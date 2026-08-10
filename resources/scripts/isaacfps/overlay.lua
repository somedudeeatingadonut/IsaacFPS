-- IsaacFPS :: lightweight stats overlay.
-- Shows smoothed FPS, frame time, entity count, Lua heap size and the current
-- detail scale. Text is rebuilt only every `overlayRefresh` frames (scaled by
-- detail); drawing itself is a few DrawString calls with a shared Font, so
-- the overlay costs far less than one mod's typical render callback.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Overlay = {}
I.Overlay = Overlay

local textCache = { lines = {}, frame = -1e9 }

local function gatherStats()
    local s = I.State
    local lines = {}
    local fps = (s.emaMs and s.emaMs > 0) and (1000 / s.emaMs) or 0
    local rgTag = (I.RG and I.RG.Active) and "  +RG" or ""
    lines[1] = string.format("FPS %.0f  (%.1f ms)%s", fps, s.emaMs or 0, rgTag)

    local l2 = ""
    if s.entityCount then
        l2 = "ents " .. s.entityCount
    end
    local mem = I.GC.MemoryKB()
    if mem then
        if l2 ~= "" then l2 = l2 .. "  " end
        l2 = l2 .. string.format("lua %.1f MB", mem / 1024)
    end
    if l2 ~= "" then lines[2] = l2 end

    if s.detail > 1 then
        lines[3] = "detail x" .. s.detail
    end
    return lines
end

local function recountEntities()
    local ok, n = pcall(function()
        local count = 0
        for _ in pairs(Isaac.GetRoomEntities()) do
            count = count + 1
        end
        return count
    end)
    I.State.entityCount = ok and n or nil
end

local function draw()
    if not I.Config.Get("overlay") then return end

    local f = Isaac.GetFrameCount()
    local refresh = math.max(2, (I.Config.Get("overlayRefresh") or 6) * I.State.detail)
    if (f - textCache.frame) >= refresh then
        textCache.lines = gatherStats()
        textCache.frame = f
    end
    if #textCache.lines == 0 then return end

    local font = I.Font()
    local size = Isaac.GetScreenSize()
    local corner = I.Config.Get("overlayCorner") or "tl"
    local margin = 8
    local lineH = 11
    local color = Color(1, 1, 1, 0.85, 0, 0, 0)

    for i, line in ipairs(textCache.lines) do
        local x, y
        if corner == "bl" or corner == "br" then
            y = size.Y - margin - (#textCache.lines - i) * lineH - 10
        else
            y = margin + (i - 1) * lineH
        end
        if corner == "tr" or corner == "br" then
            x = size.X - margin - font:GetStringWidth(line)
        else
            x = margin
        end
        font:DrawString(line, x, y, color, 0, false)
    end
end

-- Registration (unscaled: diagnostics should not be starved by autoTune).
I.AddRender(recountEntities, 30, false)
I.AddRender(draw, 1, false)

return Overlay
