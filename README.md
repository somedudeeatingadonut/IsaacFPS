# IsaacFPS

A **Binding of Isaac: Repentance** mod that raises your FPS when you have a large mod
collection. It does this by cutting the wasted per-frame work that dozens of mods pile
on top of each other, tuning Lua's garbage collector, and giving mod authors a tiny
library to make their own mods cheaper. No dependencies, no assets, nothing to
configure unless you want to.

```
[IsaacFPS] v1.0.0 loaded. Type fpshelp() in the debug console.
```

---

## What it actually does

| Feature | What it fixes |
|---|---|
| **GC tuning** | Heavy mod packs allocate thousands of small Lua tables per frame. Isaac's stock garbage collector lets garbage pile up, then hitches when a big sweep finally runs. IsaacFPS switches Lua 5.4 to a smooth incremental profile (or a generational one) so collections become many tiny, invisible steps instead of frame-stopping sweeps. |
| **Sound spam dedupe** | Wraps `SFXManager():Play` and drops a play if the exact same sound (same id + pitch) was started within the last 2 frames, or if more than 16 new sounds start in one frame. Very common in big packs: several mods re-playing the same tick/charge/menu blip every frame. Looped and delayed sounds are never touched. |
| **Debug log filter** | Rate-limits identical `Isaac.DebugString` calls. Every call is disk I/O into `log.txt`; mods that log every frame are quietly expensive. The first message passes, repeats are suppressed, and a single summary line is written. |
| **Freeze when paused** | While the game is paused the screen is static, so IsaacFPS stops dispatching render tasks entirely. Pause menus in heavy packs become free. |
| **Throttled callbacks + auto detail scaling** | Mods can register render/update work through IsaacFPS to run every Nth frame (offsets spread across frames). When your FPS drops below `targetFPS`, IsaacFPS automatically raises a global *detail scale* (x2, x3): registered overlays refresh less often, the sound-dedupe window widens, etc. When headroom returns, it scales back down. |
| **Shared Font / memoization caches** | `Font` objects are expensive, and many mods rebuild them (or recompute values) every frame. IsaacFPS hands out one shared `Font` per path and a per-frame memo cache. |
| **Diagnostics** | FPS overlay (FPS, frame time, entity count, Lua heap), `fpsbench()` benchmark with avg / 1% low / worst frame, and a frame-spike recorder (`fpsreport()`) that logs stage + entity count + Lua memory for every hitch so you can find the culprit mod/room. |

Everything is wrapped in `pcall`, every patch can be undone live, and the mod registers
exactly two game callbacks — a performance mod must never become the source of lag or
error popups itself.

## About the RAM question

Isaac (`isaac-ng.exe`) is a **32-bit process**, so no matter how much RAM your PC has,
the game + all its mods share a hard ceiling of roughly **2 GB of addressable memory**
(~3.5 GB with the Large Address Aware flag, which Repentance applies). Lua scripts
running inside the game cannot break that ceiling from the inside — that's an OS-level
limit of the process.

What IsaacFPS does instead, which is the part that actually helps:

1. **Reduces Lua memory pressure** — GC tuning, sound dedupe, log filtering and the
   caches all cut allocations, so more of that 2 GB stays free for your mods instead of
   being churned into garbage. `fpsmem()` shows you exactly how much is reclaimable.
2. **Reduces CPU/GPU work**, which is what low FPS in big packs usually is (not RAM).
3. **Recommendation for mod-heavy setups:** make sure you're running the game with the
   4 GB patch enabled (Repentance does this by default; if you patched an older
   install, re-apply LAA), close memory-hungry overlays, and keep your mod count
   audited with `fpsreport()` to find offenders.

## Install

**Steam Workshop:** subscribe when published (search "IsaacFPS").

**Manual:**
1. Find your mods folder — usually
   `Documents/My Games/Binding of Isaac Repentance/mods/`
2. Put this repo's mod folder in there, so the structure is
   `mods/isaacfps/metadata.xml`, `mods/isaacfps/resources/scripts/...`
3. Launch Repentance. You'll see the FPS overlay top-left and a console message.

## Console commands

Open the debug console (press `` ` `` with `EnableDebug` set in `options.ini`) and type:

| Command | Effect |
|---|---|
| `fpshelp()` | list all commands |
| `fps()` | current FPS, frame time, Lua memory, detail scale |
| `fpskeys()` | list every setting with its current value |
| `fpsget(key)` / `fpsset(key, value)` | read / change a setting (saved automatically) |
| `fpsoverlay()` | toggle the FPS overlay |
| `fpsbench(seconds)` | benchmark: avg FPS, 1% low, worst frame, memory growth |
| `fpsreport()` | show recorded frame spikes (stage / entities / memory per hitch) |
| `fpsmem()` | Lua heap size + how much a full GC sweep reclaims |

## Settings

All settings persist in the mod's save data. Change with `fpsset(key, value)`.

| Key | Default | Meaning |
|---|---|---|
| `overlay` | `true` | draw the stats overlay |
| `overlayCorner` | `"tl"` | `tl` / `tr` / `bl` / `br` |
| `overlayRefresh` | `6` | rebuild overlay text every N frames |
| `audioDedupe` | `true` | sound spam dedupe |
| `dedupeWindow` | `2` | frames during which identical sounds are dropped |
| `maxSoundsPerFrame` | `16` | cap of new sound starts per frame |
| `debugFilter` | `true` | debug log spam filter |
| `debugWindow` | `120` | frames during which repeated log lines are suppressed |
| `gcProfile` | `1` | `0` stock · `1` smooth (incremental) · `2` aggressive (generational + paused sweeps) |
| `freezeWhenPaused` | `true` | skip rendering while paused |
| `autoTune` | `true` | automatic detail scaling |
| `targetFPS` | `60` | what autoTune tries to keep |
| `spikeMs` | `66` | frames longer than this are recorded |
| `keepSpikes` | `40` | how many spikes to remember |

## For mod authors

IsaacFPS exposes a tiny opt-in API that makes your mod cheaper in large collections.
Nothing breaks if IsaacFPS isn't installed — just guard with `if IsaacFPS then`:

```lua
if IsaacFPS then
    -- Draw my overlay every 3rd frame instead of every frame.
    -- IsaacFPS may stretch this further automatically when the game is slow.
    IsaacFPS.AddRender(function()
        -- my drawing code
    end, 3)

    -- Expensive value, recomputed at most every 15 frames.
    local stats = IsaacFPS.Cache.Get("MyModStats", 15, function()
        return ComputeExpensiveStats()
    end)

    -- Shared font instance instead of Font("...") every frame.
    local font = IsaacFPS.Font() -- "font/luamini outlined.otf"
    font:DrawString("hello", 10, 10, Color(1, 1, 1, 1, 0, 0, 0), 0, false)
end
```

Other API: `IsaacFPS.AddUpdate(fn, interval)` (logic, runs with game updates),
`IsaacFPS.RemoveTask(handle)`, `IsaacFPS.Cache.Invalidate(key)`,
`IsaacFPS.SetDetail(n)`, `IsaacFPS.Font(path)`.

## Compatibility & safety

- Targets **Repentance** (Lua 5.4); the code avoids newer syntax and feature-detects
  GC modes, so it degrades gracefully elsewhere.
- Patches (`SFXManager().Play`, `Isaac.DebugString`) are applied through the class
  metatable, chain cleanly with other wrapping mods, and are restored exactly when you
  disable the corresponding setting (`fpsset('audioDedupe', false)`).
- Every callback body runs protected; IsaacFPS logs its own errors to `log.txt`
  (prefixed `[IsaacFPS]`) instead of raising the in-game error popup.
- If anything ever seems off, you can neutralize the whole mod by deleting its folder —
  it touches no game files.

## Repository layout

```
metadata.xml                     Repentance mod metadata
resources/scripts/main.lua       loader + frame loops
resources/scripts/isaacfps/      modules (config, gc, audio, overlay, ...)
tools/smoketest.py               dev-only: runs the mod against a stubbed Isaac API
```

### Dev: running the smoke test

```bash
pip install lupa
python3 tools/smoketest.py     # 46 assertions over every feature
```

## License

MIT — see [LICENSE](LICENSE).
