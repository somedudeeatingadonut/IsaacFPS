-- IsaacFPS :: frame spike recorder.
-- Whenever a rendered frame takes longer than `spikeMs`, we remember when it
-- happened, what stage you were on, how many entities were in the room and
-- how large the Lua heap was. Print the list with fpsreport() to hunt down
-- which rooms/mods cause the hitches.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Spikes = {}
I.Spikes = Spikes

local spikes = {}

function Spikes.Record(deltaMs)
    local entry = {
        ms = deltaMs,
        time = U.MsNow(),
        stage = nil,
        ents = I.State.entityCount,
        mem = I.GC.MemoryKB(),
    }
    pcall(function()
        local level = Game():GetLevel()
        entry.stage = tostring(level:GetStage())
    end)
    spikes[#spikes + 1] = entry
    local keep = I.Config.Get("keepSpikes") or 40
    while #spikes > keep do
        table.remove(spikes, 1)
    end
end

function Spikes.Count()
    return #spikes
end

function Spikes.Report()
    if #spikes == 0 then
        Isaac.Console("IsaacFPS: no frame spikes recorded this session. Nice.")
        return
    end
    Isaac.Console("IsaacFPS: last " .. #spikes .. " frame spikes (> "
        .. tostring(I.Config.Get("spikeMs")) .. " ms):")
    for i, s in ipairs(spikes) do
        Isaac.Console(string.format(
            "  #%02d  %6.0f ms   stage=%s  ents=%s  lua=%s",
            i, s.ms,
            tostring(s.stage or "?"),
            tostring(s.ents or "?"),
            s.mem and string.format("%.1f MB", s.mem / 1024) or "?"))
    end
    Isaac.Console("Tip: spikes that always happen in the same rooms usually point at one mod's spawns or callbacks.")
end

return Spikes
