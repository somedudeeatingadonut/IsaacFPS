# IsaacFPS native layer

A **non-mod, non-Lua** performance component that runs inside the game process
itself — the same class of technique REPENTOGON uses (DLL injection + signature
scanning + inline hooking), built as a small, single-purpose tool.

What it does today:

- **Adaptive entity-shadow shedding.** Entity shadows (enemies, tears,
  projectiles, pickups) are skipped automatically *only while the game is
  actually lagging* (frame-time based, with hysteresis), and restored when
  there is headroom again. In tear-heavy synergy rooms shadows are a large
  share of the render cost. Modes: `adaptive` (default), `always`, `never`.
- **Native frame-time measurement** via a `Game::Render` hook (installed only
  when REPENTOGON is absent — it already hooks that function).

Everything is signature-verified and reversible. See `../docs/NATIVE_PATH.md`
for the full technical writeup, honest expectations, and how to extend it.

## Install & use (Windows)

1. Copy `dist/isaacfps_native.dll` and `dist/isaacfps_injector.exe` into one
   folder (anywhere; the folder next to the game works fine).
2. Optional: copy `isaacfps_native.ini.example` to `isaacfps_native.ini`
   next to the DLL and edit it. Defaults are safe.
3. Launch Isaac (Repentance+ v1.9.7.12, with or without REPENTOGON).
4. Run `isaacfps_injector.exe`.
5. Watch `isaacfps_native.log` (created next to the DLL) — it says whether
   the hooks were installed and when adaptive mode toggles.

Remove it at any time, live:

```
isaacfps_injector.exe --eject      # unloads the DLL, restores original code
```

Kill switch without ejecting: create an empty file named `isaacfps_native.off`
next to the DLL, then eject + re-inject (or just don't inject).

## Config (`isaacfps_native.ini`)

```ini
enabled=1                # master switch
shadows=adaptive         # adaptive | always | never
target_fps=55            # below this -> consider the game lagging
recover_fps=70           # above this -> consider headroom restored
adaptive_fallback=never  # used when frame measurement is unavailable
                         # (e.g. REPENTOGON present): always | never
log=1                    # write isaacfps_native.log
```

## Safety design

- **No game files are modified.** Injection is RAM-only; ejecting restores the
  original code paths.
- **Signature-verified:** every function is located by byte signature before
  hooking. If signatures don't match (game updated), **zero hooks install**
  and the game runs unmodified — the log tells you so.
- **Kill switch:** `isaacfps_native.off` file, or `enabled=0`.
- **REPENTOGON-aware:** it never stacks a second hook on `Game::Render`.
- **Conservative hook choice:** `RenderShadowLayer` returning `false` is a
  state the engine itself produces when an entity has no shadow; no memory is
  freed, no objects are faked, no caller contracts are broken.

## Rebuilding

```bash
cd native
./build.sh          # runs unit tests, then cross-compiles with zig
```

(needs `zig` or `pip install ziglang` — zig bundles a mingw-w64 toolchain.)
