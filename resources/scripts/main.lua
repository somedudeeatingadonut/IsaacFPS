-- ===========================================================================
--  IsaacFPS  v1.0.0
--  FPS booster and performance toolkit for The Binding of Isaac: Repentance.
--
--  Designed for big mod collections. Modules:
--    isaacfps/util.lua         shared helpers
--    isaacfps/config.lua       persistent settings (moddata)
--    isaacfps/gc.lua           garbage collector tuning
--    isaacfps/throttle.lua     throttled render/update callbacks + detail scale
--    isaacfps/cache.lua        memoization + shared Font cache
--    isaacfps/audio.lua        SFXManager():Play spam dedupe
--    isaacfps/debugfilter.lua  Isaac.DebugString spam filter
--    isaacfps/overlay.lua      FPS/stats overlay
--    isaacfps/spikes.lua       frame spike recorder (fpsreport)
--    isaacfps/autotune.lua     automatic detail scaling
--    isaacfps/bench.lua        fpsbench() benchmark
--    isaacfps/commands.lua     debug console commands (fpshelp, fps, ...)
-- ===========================================================================

if IsaacFPS and IsaacFPS.Loaded then
    pcall(Isaac.DebugString, "[IsaacFPS] already loaded; skipping duplicate init.")
    return
end

local MOD_VERSION = "1.0.0"
local mod = RegisterMod("IsaacFPS", 1)

local I = {
    Mod = mod,
    Version = MOD_VERSION,
    Loaded = true,
    State = {
        detail = 1,        -- global detail multiplier (1..3), set by autoTune
        emaMs = nil,       -- smoothed frame time in ms
        entityCount = nil, -- entities in current room (recounted periodically)
    },
}
_G.IsaacFPS = I

-- Load order matters: util and config first, everything else after.
include("isaacfps/util.lua")
include("isaacfps/config.lua")
include("isaacfps/gc.lua")
include("isaacfps/throttle.lua")
include("isaacfps/cache.lua")
include("isaacfps/audio.lua")
include("isaacfps/debugfilter.lua")
include("isaacfps/overlay.lua")
include("isaacfps/spikes.lua")
include("isaacfps/autotune.lua")
include("isaacfps/bench.lua")
include("isaacfps/commands.lua")

local U = I.Util

-- ---------------------------------------------------------------------------
-- Settings changes apply live.
-- ---------------------------------------------------------------------------
I.Config.Watchers.audioDedupe = function(v)
    if v then I.Audio.Patch() else I.Audio.Unpatch() end
end
I.Config.Watchers.debugFilter = function(v)
    if v then I.DebugFilter.Patch() else I.DebugFilter.Unpatch() end
end
I.Config.Watchers.gcProfile = function(v)
    I.GC.Apply(v)
end
I.Config.Watchers.autoTune = function(v)
    if not v then I.SetDetail(1) end -- manual control: reset to normal
end

-- ---------------------------------------------------------------------------
-- Boot: load saved settings, then apply them.
-- ---------------------------------------------------------------------------
I.Config.Load()

U.Try("gc init", function()
    I.GC.Apply(I.Config.Get("gcProfile"))
end)
U.Try("audio init", function()
    if I.Config.Get("audioDedupe") then I.Audio.Patch() end
end)
U.Try("debug filter init", function()
    if I.Config.Get("debugFilter") then I.DebugFilter.Patch() end
end)

-- ---------------------------------------------------------------------------
-- The frame loops. Exactly two callbacks from this mod; all module work is
-- dispatched through them, and everything runs protected so IsaacFPS can
-- never become the cause of error popups or stutter.
-- ---------------------------------------------------------------------------
local lastRenderMs = nil

local function onRender()
    U.Try("render loop", function()
        local now = Isaac.GetTime()

        -- Frame time accounting + spike detection.
        if lastRenderMs then
            local delta = now - lastRenderMs
            if delta >= 0 and delta < 5000 then
                local s = I.State
                if s.emaMs then
                    s.emaMs = s.emaMs * 0.9 + delta * 0.1
                else
                    s.emaMs = delta
                end
                if delta > (I.Config.Get("spikeMs") or 66) then
                    U.Try("spike record", function() I.Spikes.Record(delta) end)
                end
            end
        end
        lastRenderMs = now

        -- Freeze mod rendering while paused (screen is static anyway).
        local paused = false
        pcall(function() paused = Game():IsPaused() end)
        if paused and I.Config.Get("freezeWhenPaused") then
            return
        end

        local frame = Isaac.GetFrameCount()
        I.Throttle.RunRender(frame)
        if frame % 30 == 0 then
            U.Try("autotune", I.AutoTune.Tick)
        end
    end)
end

local gcTickCounter = 0
local function onUpdate()
    U.Try("update loop", function()
        I.Throttle.RunUpdate(Isaac.GetFrameCount())

        -- Profile 2 GC: reclaim memory in small steps while paused.
        gcTickCounter = gcTickCounter + 1
        if gcTickCounter >= 60 then
            gcTickCounter = 0
            local paused = false
            pcall(function() paused = Game():IsPaused() end)
            if paused then
                U.Try("gc maintenance", I.GC.MaintenanceTick)
            end
        end
    end)
end

mod:AddCallback(ModCallback.POST_RENDER, onRender)
mod:AddCallback(ModCallback.POST_UPDATE, onUpdate)

if ModCallback.PRE_GAME_EXIT then
    mod:AddCallback(ModCallback.PRE_GAME_EXIT, function()
        U.Try("save on exit", function() I.Config.Save() end)
        U.Try("gc on exit", function()
            if type(collectgarbage) == "function" then
                pcall(collectgarbage, "collect")
            end
        end)
    end)
end

Isaac.Console("[IsaacFPS] v" .. MOD_VERSION .. " loaded. Type fpshelp() in the debug console.")
U.Log("Initialized: overlay=" .. tostring(I.Config.Get("overlay"))
    .. " audioDedupe=" .. tostring(I.Config.Get("audioDedupe"))
    .. " debugFilter=" .. tostring(I.Config.Get("debugFilter"))
    .. " gcProfile=" .. tostring(I.Config.Get("gcProfile"))
    .. " autoTune=" .. tostring(I.Config.Get("autoTune")))
