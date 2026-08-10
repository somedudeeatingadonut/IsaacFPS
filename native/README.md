# IsaacFPS native layer

A **non-mod, non-Lua** performance component that runs inside the game process
itself — the same class of technique REPENTOGON uses (DLL injection + signature
scanning + inline hooking), built as a small, single-purpose tool.

What it does today:

- **Adaptive cosmetic-render shedding.** While the game is actually lagging
  (frame-time based, with hysteresis) it skips:
  - entity shadow layers (enemies, tears, projectiles, pickups — huge in
    tear-heavy synergy rooms),
  - ground-impact cosmetic effects (`DoGroundImpactEffects`).
  Everything is restored automatically when headroom returns. Modes:
  `adaptive` (default), `always`, `never`.
- **Native frame-time measurement**, source chosen automatically:
  `Game::Render` (one sample per rendered frame) when REPENTOGON is absent,
  `Level::Update` (30 Hz logic ticks, normalized to frame equivalents) when
  REPENTOGON is present, since REPENTOGON already hooks `Game::Render` and
  hooks must never be stacked.
- **Uniqueness-enforced signature scanning:** a signature must match exactly
  once in the executable image or the hook is refused (no guessing on short
  signatures).

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
ground_impacts=1         # also skip ground-impact FX while shedding
adaptive_fallback=never  # last resort if NO measurement source works
log=1                    # write isaacfps_native.log
```

## Safety design

- **No game files are modified.** Injection is RAM-only; ejecting restores the
  original code paths.
- **Signature-verified:** every function is located by byte signature before
  hooking. If signatures don't match (game updated), **zero hooks install**
  and the game runs unmodified — the log tells you so.
- **Kill switch:** `isaacfps_native.off` file, or `enabled=0`.
- **REPENTOGON-aware:** it never stacks a hook on any function REPENTOGON
  already hooks (`Game::Render`, `Room::RenderEntityLight`, ...); with
  REPENTOGON present it measures lag via `Level::Update` instead.
- **Uniqueness-enforced scanning:** signatures must match exactly once in the
  executable image, or the hook is refused.
- **Conservative hook choice:** `RenderShadowLayer` returning `false` is a
  state the engine itself produces when an entity has no shadow; no memory is
  freed, no objects are faked, no caller contracts are broken.

## Rebuilding

```bash
cd native
./build.sh          # runs unit tests, then cross-compiles with zig
```

(needs `zig` or `pip install ziglang` — zig bundles a mingw-w64 toolchain.)
