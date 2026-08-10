-- ===========================================================================
--  IsaacFPS  v1.1.0
--  FPS booster and performance toolkit for The Binding of Isaac: Repentance.
--
--  Designed for big mod collections. Modules:
--    isaacfps/util.lua         shared helpers
--    isaacfps/config.lua       persistent settings (moddata)
--    isaacfps/gc.lua           garbage collector tuning
--    isaacfps/throttle.lua     throttled render/update callbacks + detail scale
--    isaacfps/cache.lua        memoization + shared Font cache
--    isaacfps/audio.lua        sound spam dedupe (native or wrapper)
--    isaacfps/debugfilter.lua  Isaac.DebugString spam filter
--    isaacfps/overlay.lua      FPS/stats overlay
--    isaacfps/spikes.lua       frame spike recorder (fpsreport)
--    isaacfps/autotune.lua     automatic detail scaling
--    isaacfps/bench.lua        fpsbench() benchmark
--    isaacfps/commands.lua     debug console commands (fpshelp, fps, ...)
--    isaacfps/repentogon.lua   optional REPENTOGON integration (detects it:
--                              native sfx hook, console API, ImGui dashboard,
--                              nanosecond timing, GC awareness)
-- ===========================================================================

if IsaacFPS and IsaacFPS.Loaded then
    pcall(Isaac.DebugString, "[IsaacFPS] already loaded; skipping duplicate init.")
    return
end

local MOD_VERSION = "1.1.0"
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

-- Callback enum resolution: Repentance uses ModCallbacks.MC_*, older ports
-- used ModCallback.*; fall back to raw numeric ids if all else fails.
local MC = ModCallbacks or ModCallback or {}
local CB_POST_UPDATE    = MC.MC_POST_UPDATE    or MC.POST_UPDATE    or 1
local CB_POST_RENDER    = MC.MC_POST_RENDER    or MC.POST_RENDER    or 2
local CB_PRE_GAME_EXIT  = MC.MC_PRE_GAME_EXIT  or MC.PRE_GAME_EXIT

-- Load order matters: util and config first, repentogon last (its detection
-- must finish before the boot section applies settings below).
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
include("isaacfps/repentogon.lua")

local U = I.Util

-- ---------------------------------------------------------------------------
-- Settings changes apply live.
-- ---------------------------------------------------------------------------
I.Config.Watchers.audioDedupe = function(v)
    if I.Audio.Native then return end -- the native hook checks the setting live
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
    if I.Config.Get("audioDedupe") then
        local nativeOk = I.RG.HasPreSfxCallback and I.Audio.PatchNative()
        if not nativeOk then
            I.Audio.Patch()
        end
    end
end)
U.Try("debug filter init", function()
    if I.Config.Get("debugFilter") then I.DebugFilter.Patch() end
end)
U.Try("repentogon ui init", function()
    I.RG.InitConsole()
    I.RG.InitImGui()
end)

-- ---------------------------------------------------------------------------
-- The frame loops. Exactly two callbacks from this mod; all module work is
-- dispatched through them, and everything runs protected so IsaacFPS can
-- never become the cause of error popups or stutter.
-- ---------------------------------------------------------------------------
local lastRenderMs = nil

local function onRender()
    U.Try("render loop", function()
        local now = U.MsNow()

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

mod:AddCallback(CB_POST_RENDER, onRender)
mod:AddCallback(CB_POST_UPDATE, onUpdate)

if CB_PRE_GAME_EXIT then
    mod:AddCallback(CB_PRE_GAME_EXIT, function()
        U.Try("save on exit", function() I.Config.Save() end)
        U.Try("gc on exit", function()
            if type(collectgarbage) == "function" then
                pcall(collectgarbage, "collect")
            end
        end)
    end)
end

Isaac.Console("[IsaacFPS] v" .. MOD_VERSION .. " loaded"
    .. (I.RG.Active and (" (REPENTOGON " .. tostring(I.RG.Version) .. " detected)") or "")
    .. ". Type fpshelp() in the debug console.")
U.Log("Initialized: overlay=" .. tostring(I.Config.Get("overlay"))
    .. " audioDedupe=" .. tostring(I.Config.Get("audioDedupe"))
    .. (I.Audio.Native and " (native hook)" or "")
    .. " debugFilter=" .. tostring(I.Config.Get("debugFilter"))
    .. " gcProfile=" .. tostring(I.Config.Get("gcProfile"))
    .. " autoTune=" .. tostring(I.Config.Get("autoTune")))
