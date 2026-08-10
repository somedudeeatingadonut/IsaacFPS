-- IsaacFPS :: automatic detail scaling.
-- Every ~30 frames we compare the smoothed FPS against `targetFPS`:
--   * sustained drop below 90% of target  -> raise detail scale (coarser),
--   * sustained headroom above 135%       -> lower detail scale again.
-- The detail scale stretches the intervals of every IsaacFPS.AddRender /
-- AddUpdate callback registered by mods, the overlay refresh interval and
-- the sound dedupe window, so under load the collection does less per-frame
-- work automatically instead of snowballing into a slideshow.

local I = IsaacFPS
if not I then return end
local U = I.Util

local AutoTune = {}
I.AutoTune = AutoTune

local lowChecks = 0
local highChecks = 0
local cooldown = 0

function AutoTune.Tick()
    if not I.Config.Get("autoTune") then return end

    local emaMs = I.State.emaMs
    if not emaMs or emaMs <= 0 then return end
    if cooldown > 0 then cooldown = cooldown - 1 end

    local target = I.Config.Get("targetFPS") or 60
    local fps = 1000 / emaMs

    if fps < target * 0.9 then
        lowChecks = lowChecks + 1
        highChecks = 0
    elseif fps > target * 1.35 then
        highChecks = highChecks + 1
        lowChecks = 0
    else
        lowChecks = 0
        highChecks = 0
    end

    if lowChecks >= 2 and cooldown == 0 and I.State.detail < 3 then
        I.SetDetail(I.State.detail + 1)
        Isaac.Console(string.format(
            "[IsaacFPS] running below %d fps -> detail scale raised to x%d (mod overlays refresh less often).",
            target, I.State.detail))
        lowChecks = 0
        cooldown = 4
    elseif highChecks >= 5 and cooldown == 0 and I.State.detail > 1 then
        I.SetDetail(I.State.detail - 1)
        Isaac.Console(string.format(
            "[IsaacFPS] headroom restored -> detail scale back to x%d.",
            I.State.detail))
        highChecks = 0
        cooldown = 4
    end
end

return AutoTune
