-- IsaacFPS :: quick FPS benchmark.
-- fpsbench(seconds) samples every rendered frame for the given duration and
-- then reports average FPS, the 1% low (worst 1% of frames) and the worst
-- single frame, plus Lua memory growth. Use it before/after enabling heavy
-- mods or tweaking IsaacFPS settings to see real numbers.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Bench = {}
I.Bench = Bench

local handle = nil
local state = nil

local function finish()
    if not state then return end
    local s = state
    state = nil
    if handle then
        I.RemoveTask(handle)
        handle = nil
    end
    if #s.deltas == 0 then
        Isaac.Console("IsaacFPS bench: no frames sampled.")
        return
    end

    table.sort(s.deltas)
    local n = #s.deltas
    local sum = 0
    for _, d in ipairs(s.deltas) do sum = sum + d end
    local avgMs = sum / n

    local lowCount = math.max(1, math.floor(n * 0.01))
    local lowSum = 0
    for i = 1, lowCount do
        lowSum = lowSum + s.deltas[n - i + 1] -- longest frames = worst
    end

    Isaac.Console(string.format(
        "IsaacFPS bench (%.1fs, %d frames): avg %.1f fps | 1%% low %.1f fps | worst frame %.1f ms",
        (U.MsNow() - s.startTime) / 1000, n,
        1000 / avgMs, 1000 / (lowSum / lowCount), s.deltas[n]))

    local memNow = I.GC.MemoryKB()
    if memNow and s.startMem then
        Isaac.Console(string.format("IsaacFPS bench: lua memory %.1f MB -> %.1f MB",
            s.startMem / 1024, memNow / 1024))
    end
end

local function sample()
    if not state then return end
    local s = state
    local now = U.MsNow()
    if s.lastT then
        local d = now - s.lastT
        if d >= 0 and d < 5000 then
            s.deltas[#s.deltas + 1] = d
        end
    end
    s.lastT = now
    if now - s.startTime >= s.duration then
        finish()
    end
end

function Bench.Run(seconds)
    if state then
        Isaac.Console("IsaacFPS: a bench is already running.")
        return
    end
    seconds = math.max(1, math.min(60, tonumber(seconds) or 5))
    state = {
        startTime = U.MsNow(),
        duration = seconds * 1000,
        deltas = {},
        lastT = nil,
        startMem = I.GC.MemoryKB(),
    }
    handle = I.AddRender(sample, 1, false)
    Isaac.Console(string.format("IsaacFPS: sampling frames for %d second(s)...", seconds))
end

return Bench
