-- IsaacFPS :: throttled callback library + detail scaling.
-- Other mods can register render/update callbacks through IsaacFPS and get:
--   * execution every Nth frame instead of every frame,
--   * offsets spread across frames so many tasks don't land on the same one,
--   * automatic coarsening ("detail scale") when the game runs slow.
-- The detail scale is what autoTune adjusts; it also stretches the sound
-- dedupe window and the overlay refresh interval.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Throttle = {}
I.Throttle = Throttle

I.State = I.State or {}
I.State.detail = I.State.detail or 1

local nextOffset = 0
local renderTasks = {}
local updateTasks = {}

local function addTask(list, fn, interval, scaled)
    interval = math.max(1, math.floor(tonumber(interval) or 1))
    local task = {
        fn = fn,
        interval = interval,
        scaled = (scaled ~= false),
        alive = true,
    }
    task.offset = nextOffset % interval
    nextOffset = nextOffset + 1
    list[#list + 1] = task
    return task
end

-- Public API for other mods ----------------------------------------------
-- Returns a handle; pass it to IsaacFPS.RemoveTask(handle) to unregister.
function I.AddRender(fn, interval, scaled)
    return addTask(renderTasks, fn, interval, scaled)
end

function I.AddUpdate(fn, interval, scaled)
    return addTask(updateTasks, fn, interval, scaled)
end

function I.RemoveTask(handle)
    if type(handle) == "table" then handle.alive = false end
end

-- detail: 1 = normal, 2 = coarser, 3 = coarsest.
function I.SetDetail(n)
    n = U.Clamp(math.floor(tonumber(n) or 1), 1, 3)
    if n ~= I.State.detail then
        I.State.detail = n
        U.Log("Detail scale set to x" .. n)
    end
end
----------------------------------------------------------------------------

local function runList(list, frame)
    local detail = I.State.detail
    local i = 1
    while i <= #list do
        local t = list[i]
        if not t.alive then
            list[i] = list[#list]
            list[#list] = nil
        else
            local iv = t.interval * (t.scaled and detail or 1)
            if (frame + t.offset) % iv == 0 then
                U.Try("throttled task", t.fn)
            end
            i = i + 1
        end
    end
end

function Throttle.RunRender(frame) runList(renderTasks, frame) end
function Throttle.RunUpdate(frame) runList(updateTasks, frame) end

return Throttle
