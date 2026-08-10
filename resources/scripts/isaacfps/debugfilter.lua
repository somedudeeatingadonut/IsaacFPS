-- IsaacFPS :: debug log spam filter.
-- Isaac.DebugString writes to the game's log file. Mods that call it every
-- frame (intentionally or not) cause constant disk I/O. We suppress exact
-- repeats of the previous message within `debugWindow` frames and log a
-- single summary line about what was suppressed.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Filter = {}
I.DebugFilter = Filter

Filter.Patched = false

local lastMsg = nil
local lastFrame = -1e9
local suppressed = 0

local function wrappedDebugString(msg, isError)
    if not I.Config.Get("debugFilter") then
        return I.OrigDebugString(msg, isError)
    end

    local f = Isaac.GetFrameCount()
    if msg == lastMsg and (f - lastFrame) < (I.Config.Get("debugWindow") or 120) then
        suppressed = suppressed + 1
        lastFrame = f
        return
    end

    if suppressed > 0 then
        I.OrigDebugString("[IsaacFPS] previous message repeated x" .. suppressed .. " (suppressed)")
        suppressed = 0
    end
    lastMsg = msg
    lastFrame = f
    return I.OrigDebugString(msg, isError)
end

function Filter.Patch()
    if Filter.Patched then return end
    if type(Isaac.DebugString) ~= "function" then return end
    Isaac.DebugString = wrappedDebugString
    Filter.Patched = true
    U.Log("Debug log filter active.")
end

function Filter.Unpatch()
    if not Filter.Patched then return end
    Isaac.DebugString = I.OrigDebugString
    Filter.Patched = false
    U.Log("Debug log filter disabled.")
end

return Filter
