-- IsaacFPS :: persistent configuration.
-- Stored through the mod's own save data (moddata) as tagged key:value lines
-- so types survive a save/load round trip:  key:t:value  with t in b/n/s.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Config = {}
I.Config = Config

Config.Defaults = {
    -- FPS overlay
    overlay        = true,    -- draw the stats overlay?
    overlayCorner  = "tl",    -- tl | tr | bl | br
    overlayRefresh = 6,       -- rebuild the overlay text every N frames
    -- Sound spam dedupe
    audioDedupe       = true, -- wrap SFXManager():Play to drop duplicate spam
    dedupeWindow      = 2,    -- same sound within N frames is dropped
    maxSoundsPerFrame = 16,   -- hard cap of new plays started per frame
    -- Debug log spam filter
    debugFilter = true,       -- rate-limit identical Isaac.DebugString calls
    debugWindow = 120,        -- frames during which repeats are suppressed
    -- Garbage collection
    gcProfile = 1,            -- 0 = stock, 1 = smooth, 2 = aggressive
    -- Behaviour
    freezeWhenPaused = true,  -- skip overlay/mod rendering while paused
    autoTune         = true,  -- raise/lower detail scale automatically
    targetFPS        = 60,    -- what autoTune tries to keep
    -- Diagnostics
    spikeMs    = 66,          -- frame longer than this is recorded as a spike
    keepSpikes = 40,          -- how many spikes to remember
}

Config.Values = {}
for k, v in pairs(Config.Defaults) do Config.Values[k] = v end

-- Short per-key descriptions, used by the REPENTOGON console autocomplete.
Config.Help = {
    overlay        = "draw the FPS/stats overlay",
    overlayCorner  = "overlay corner: tl, tr, bl or br",
    overlayRefresh = "rebuild overlay text every N frames",
    audioDedupe    = "drop duplicate/spammed sound plays",
    dedupeWindow   = "frames during which identical sounds are dropped",
    maxSoundsPerFrame = "cap of new sound starts per frame",
    debugFilter    = "suppress repeated Isaac.DebugString calls",
    debugWindow    = "frames during which repeated log lines are suppressed",
    gcProfile      = "0 stock, 1 smooth, 2 aggressive",
    freezeWhenPaused = "skip mod rendering while paused",
    autoTune       = "automatic detail scaling when FPS drops",
    targetFPS      = "what autoTune tries to keep",
    spikeMs        = "frames longer than this are recorded as spikes",
    keepSpikes     = "how many spikes to remember",
}

Config.Watchers = {} -- key -> function(newValue), called by Config.Set

function Config.Serialize()
    local lines = {}
    for k, v in pairs(Config.Values) do
        local t = type(v)
        if t == "boolean" then
            lines[#lines + 1] = k .. ":b:" .. (v and "1" or "0")
        elseif t == "number" then
            lines[#lines + 1] = k .. ":n:" .. tostring(v)
        elseif t == "string" then
            lines[#lines + 1] = k .. ":s:" .. v
        end
    end
    return table.concat(lines, "\n")
end

function Config.Deserialize(str)
    for line in tostring(str):gmatch("[^\r\n]+") do
        local k, t, v = line:match("^([%w_]+):([bns]):(.*)$")
        if k and Config.Defaults[k] ~= nil then
            if t == "b" then
                Config.Values[k] = (v == "1")
            elseif t == "n" then
                Config.Values[k] = tonumber(v) or Config.Defaults[k]
            else
                Config.Values[k] = v
            end
        end
    end
end

function Config.Load()
    local ok = pcall(function()
        if I.Mod:HasModData() then
            Config.Deserialize(I.Mod:LoadModData())
        end
    end)
    if not ok then
        U.Log("Could not read saved config; using defaults.")
    end
end

function Config.Save()
    pcall(function() I.Mod:SaveModData(Config.Serialize()) end)
end

function Config.Get(key)
    return Config.Values[key]
end

function Config.Set(key, value)
    if Config.Defaults[key] == nil then
        U.Log("Unknown config key: " .. tostring(key))
        return false
    end
    local dt = type(Config.Defaults[key])
    if dt == "boolean" and type(value) ~= "boolean" then
        value = (value == true or value == 1 or value == "1" or value == "true")
    elseif dt == "number" then
        value = tonumber(value) or Config.Defaults[key]
    elseif dt == "string" then
        value = tostring(value)
    end
    Config.Values[key] = value
    Config.Save()
    local w = Config.Watchers[key]
    if w then
        U.Try("config watcher " .. key, function() w(value) end)
    end
    return true
end

return Config
