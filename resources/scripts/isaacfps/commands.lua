-- IsaacFPS :: debug console commands.
-- The Isaac debug console evaluates Lua, so short global functions are the
-- user interface. Everything is also reachable through the IsaacFPS table.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Commands = {}
I.Commands = Commands

local HELP = {
    "IsaacFPS console commands (type exactly as shown):",
    "  fpshelp()          this list",
    "  fps()              status: fps, frame time, memory, detail scale",
    "  fpskeys()          list every setting and its current value",
    "  fpsget(key)        read one setting",
    "  fpsset(key, value) change one setting (saved automatically)",
    "  fpsoverlay()       toggle the FPS overlay",
    "  fpsbench(seconds)  benchmark the next N seconds (default 5)",
    "  fpsreport()        show recorded frame spikes",
    "  fpsmem()           Lua memory report + full GC sweep",
}

function _G.fpshelp()
    for _, l in ipairs(HELP) do Isaac.Console(l) end
end

function _G.fpskeys()
    local keys = {}
    for k in pairs(I.Config.Defaults) do keys[#keys + 1] = k end
    table.sort(keys)
    for _, k in ipairs(keys) do
        Isaac.Console(string.format("  %s = %s", k, tostring(I.Config.Get(k))))
    end
end

function _G.fpsget(key)
    Isaac.Console("IsaacFPS: " .. tostring(key) .. " = " .. tostring(I.Config.Get(key)))
end

function _G.fpsset(key, value)
    if I.Config.Set(key, value) then
        Isaac.Console("IsaacFPS: " .. tostring(key) .. " = " .. tostring(I.Config.Get(key)))
    else
        Isaac.Console("IsaacFPS: unknown key '" .. tostring(key) .. "'. Try fpskeys().")
    end
end

function _G.fpsoverlay()
    _G.fpsset("overlay", not I.Config.Get("overlay"))
end

function _G.fpsbench(seconds)
    I.Bench.Run(seconds)
end

function _G.fpsreport()
    I.Spikes.Report()
end

function _G.fpsmem()
    local before = I.GC.MemoryKB()
    if not before then
        Isaac.Console("IsaacFPS: collectgarbage() is not available here.")
        return
    end
    pcall(collectgarbage, "collect")
    local after = I.GC.MemoryKB() or before
    Isaac.Console(string.format(
        "IsaacFPS: lua heap %.2f MB, after full sweep %.2f MB (%.2f MB was reclaimable)",
        before / 1024, after / 1024, (before - after) / 1024))
end

function _G.fps()
    local s = I.State
    local fps = (s.emaMs and s.emaMs > 0) and (1000 / s.emaMs) or 0
    Isaac.Console(string.format("IsaacFPS v%s | %.0f fps (%.1f ms) | detail x%d",
        I.Version, fps, s.emaMs or 0, s.detail))
    local mem = I.GC.MemoryKB()
    if mem then
        Isaac.Console(string.format("  lua memory: %.2f MB", mem / 1024))
    end
    if s.entityCount then
        Isaac.Console("  entities in room: " .. s.entityCount)
    end
    Isaac.Console("  type fpshelp() for all commands")
end

I.Help = _G.fpshelp

return Commands
