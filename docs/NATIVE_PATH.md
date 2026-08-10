# The native path: going outside Isaac's mod framework

This document is the technical writeup for `native/` — what REPENTOGON
actually does under the hood (verified from its open-source repository),
what IsaacFPS-native builds on top of that approach, what it can and cannot
fix, and where the next native levers are.

---

## 1. How REPENTOGON works (from its source)

REPENTOGON is not a Lua mod. It is a native Windows component in four layers
(repo paths below refer to `github.com/TeamREPENTOGON/REPENTOGON`):

1. **Injection.** `loader/loader.cpp` runs inside `isaac-ng.exe` (32-bit),
   brought in by a DLL-injection library (`libs/injector`, the classic
   `CreateRemoteThread` + `LoadLibrary` technique).

2. **Import-table surgery.** The loader walks the game's PE import directory
   and redirects every import of `Lua5.3.3r.dll` to a bundled `Lua5.4.dll`
   (`RedirectLua` in `loader/loader.cpp`). *This* is how Repentance ends up
   running Lua 5.4 — and therefore how its generational garbage collector
   becomes the default for every mod. It then loads `libzhl.dll` and the main
   `repentogon` module.

3. **Signature-based hooking.** `libzhl/HookSystem.cpp` resolves game
   functions at runtime by **byte signatures**:
   `SigScan scanner(signature)`. The signatures live in `libzhl/functions/*.zhl`
   files, e.g.

   ```
   "558bec83e4c081ecb4000000f30f1005":
   __thiscall bool Entity::RenderShadowLayer(Vector *offset);
   ```

   Those files were produced by reverse-engineering the game binary in Ghidra
   (`ghidra_scripts/makesig.py`) and are tied to a specific build — currently
   Repentance+ v1.9.7.12.

4. **Hooks.** 200+ `.cpp` files use a `HOOK_METHOD(Class, Method, ...)` macro
   to detour game functions: `Game::Update`, `Game::Render`, `Manager::Render`,
   `Entity_Laser::ClearLaserSamples`, `OptionsConfig::Load`, ... This is where
   all of REPENTOGON's engine-level features and fixes live (error-isolated
   callbacks, fast lasers, eco mode, the Lua API extensions, etc.).

## 2. What IsaacFPS-native does with the same mechanism

`native/` is a minimal, single-purpose tool using the exact same pipeline:

| Step | IsaacFPS-native |
|---|---|
| Injection | `isaacfps_injector.exe` (`CreateRemoteThread` + `LoadLibraryA`), plus `--eject` to unload and restore |
| Hooking library | MinHook (MIT), the standard inline-hook library for x86 |
| Signatures | Copied verbatim from REPENTOGON's published `.zhl` database for the current game build |
| Hooks | `Entity::RenderShadowLayer` (skip decision), `Game::Render` (frame timing only) |
| Brains | `adaptive.c`: frame-time EMA + hysteresis state machine deciding when to shed shadows |

### Why entity shadows first

- **Cost:** every enemy, tear, projectile and pickup renders a shadow layer.
  Tear-heavy rooms (synergy builds, Mom's Heart, Delirium) multiply that by
  hundreds — exactly the "laggy areas" case.
- **Safety:** the detour only ever returns `false`, a state the engine itself
  produces when an entity has no shadow. It never fakes objects, frees memory,
  or changes caller-visible state beyond that bool.
- **Measurability:** adaptive mode means you get the visual game back the
  moment FPS recovers, and the log records every toggle.

## 3. Honest expectations

- This layer reduces **rendering** cost. If your 40 FPS comes from entity
  shadows/fill, expect visible improvement in exactly those rooms; the log and
  the IsaacFPS overlay (`fpsbench`) will show it.
- It **cannot** speed up mod Lua logic. If thirty mods run heavy `POST_UPDATE`
  callbacks, no native hook helps — that work has to be reduced (trim mods,
  move their overlays to `IsaacFPS.AddRender(fn, N)`, or let REPENTOGON's
  error isolation stop broken mods from dragging the rest down).
- Repentance's engine is single-threaded and submission-bound; nobody has
  produced a general +50% engine patch, and REPENTOGON's own native
  optimizations are modest for the same reason. Treat claims otherwise with
  suspicion.

## 4. Safety model

- No game files touched; ejecting restores original code.
- Signature mismatch (game update) ⇒ zero hooks, game unmodified, log explains.
- Kill switch file (`isaacfps_native.off`) and `enabled=0` config.
- Never stacks a second hook onto `Game::Render` when REPENTOGON is loaded.
- The hook choice avoids any function whose callers don't tolerate the
  documented return value. (Contrast: making `MakeBloodPoof` return null would
  risk null-deref callers — deliberately not done.)
- Isaac is single-player with no anti-tamper; still, injection tools run at
  your own discretion — keep the eject command handy and verify game files
  through Steam if anything ever seems off.

## 5. Extending it (next hook candidates)

Adding a hook = one signature + one detour. Candidate levers, in rough order
of safety/impact (signatures available in REPENTOGON's `.zhl` files):

1. `GridEntity` shadow/decoration render variants (same pattern as the entity
   shadow hook).
2. Ground impact / blood poof *frequency* throttling (rate-limit calls rather
   than null them — safer than skipping outright).
3. Particle-effect LOD for `EntityEffect` updates in high-entity rooms.
4. A native FPS limiter hook around `Manager::Render` for VSync-off setups
   (cuts CPU/GPU waste in menus; smooths pacing).

Each must be validated against the current game build's signatures before
shipping, exactly as the shadow hook was.

## 6. Building

`native/build.sh` runs the host-side unit tests (sigscan/adaptive/config,
plain C on gcc) and cross-compiles the DLL/EXE with zig's bundled
mingw-w64 (`-target x86-windows-gnu`, 32-bit to match `isaac-ng.exe`).
