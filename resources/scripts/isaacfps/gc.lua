-- IsaacFPS :: garbage collector tuning.
-- Big mod collections allocate a LOT of small Lua tables every frame (callback
-- args, entity lists, strings). The stock GC settings let garbage pile up
-- and then cause visible hitches when a big collection finally runs.
--
-- Profile 0: leave the game's GC untouched.
-- Profile 1 (default): incremental GC with a low pause threshold -> many
--          small, cheap collections instead of few big ones.
-- Profile 2: generational GC (Lua 5.4+) which is excellent for workloads
--          that churn short-lived tables; plus a tiny explicit step while
--          the game is paused so memory is returned without combat jank.

local I = IsaacFPS
if not I then return end
local U = I.Util

local GC = {}
I.GC = GC

GC.HasControl = (type(collectgarbage) == "function")
GC.ActiveProfile = nil

local function tryGC(op, a, b, c)
    if not GC.HasControl then return false end
    return select(1, pcall(collectgarbage, op, a, b, c))
end

function GC.MemoryKB()
    if not GC.HasControl then return nil end
    local ok, kb = pcall(collectgarbage, "count")
    if ok and type(kb) == "number" then return kb end
    return nil
end

function GC.Apply(profile)
    if not GC.HasControl then
        U.Log("collectgarbage() is not available here; GC tuning disabled.")
        return
    end
    profile = tonumber(profile) or 1
    GC.ActiveProfile = profile

    if profile == 0 then
        U.Log("GC profile: stock (untouched).")
        return
    end

    if profile == 1 and I.RG and I.RG.Active then
        -- REPENTOGON already runs Lua 5.4's generational GC by default,
        -- which is better than anything we would configure here. Leave it.
        U.Log("GC profile: smooth requested, but REPENTOGON's generational GC default is already optimal; leaving untouched.")
        return
    end

    if profile == 2 then
        if tryGC("generational", 20, 100) then
            U.Log("GC profile: generational (aggressive).")
            return
        end
        -- Fall through to smooth on engines without generational mode.
    end

    if tryGC("incremental", 120, 150, 12) then
        U.Log("GC profile: incremental (smooth).")
        return
    end

    -- Pre-5.4 fallback knobs.
    tryGC("setpause", 120)
    tryGC("setstepmul", 150)
    U.Log("GC profile: smooth (compatibility mode).")
end

-- Called roughly every 2 seconds while the game is paused (profile 2 only).
function GC.MaintenanceTick()
    if GC.ActiveProfile == 2 then
        tryGC("step", 32)
    end
end

return GC
