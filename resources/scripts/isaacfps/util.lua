-- IsaacFPS :: shared helpers used by every module.
-- Loaded first from main.lua. Expects the global IsaacFPS table to exist.

local I = IsaacFPS
if not I then return end

local Util = {}
I.Util = Util

-- Capture the original Isaac.DebugString BEFORE our optional log filter wraps
-- it, so our own diagnostics always reach the log file.
I.OrigDebugString = Isaac.DebugString

local function rawLog(msg)
    local fn = I.OrigDebugString or Isaac.DebugString
    pcall(fn, "[IsaacFPS] " .. tostring(msg))
end

Util.Log = rawLog

-- Errors raised by our own features are logged (throttled) instead of
-- propagating into the game's error popup. A performance mod must never
-- become a source of FPS loss itself.
local errCounts = {}
function Util.Error(label, err)
    rawLog("ERROR (" .. tostring(label) .. "): " .. tostring(err))
end

function Util.Try(label, fn)
    local ok, err = pcall(fn)
    if not ok then
        local f = Isaac.GetFrameCount()
        local e = errCounts[label]
        if not e then
            e = { n = 0, last = -1e9 }
            errCounts[label] = e
        end
        e.n = e.n + 1
        if f - e.last > 300 then
            e.last = f
            rawLog("ERROR in " .. tostring(label) .. " (x" .. e.n .. "): " .. tostring(err))
        end
    end
    return ok
end

-- Lua 5.1 / LuaJIT compatibility shims (Repentance is 5.4, but be nice).
Util.Pack = table.pack or function(...) return { n = select("#", ...), ... } end
Util.Unpack = table.unpack or unpack

function Util.Clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

function Util.MsNow()
    return Isaac.GetTime()
end

return Util
