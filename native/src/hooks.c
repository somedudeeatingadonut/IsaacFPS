/* IsaacFPS native :: game hooks (Windows only).
 *
 * Mechanism: same approach REPENTOGON uses (libzhl) — locate functions in
 * isaac-ng.exe by byte signature, then install inline detours. Signatures
 * below are taken from REPENTOGON's open symbol database (the .zhl files
 * under libzhl/functions) which matches Repentance+ v1.9.7.12.
 *
 * Safety rules this file follows:
 *  - Every signature must match EXACTLY ONCE in the executable image;
 *    ambiguous (short) signatures are refused rather than guessed.
 *  - Never hook a function REPENTOGON already hooks (it maintains its own
 *    hook chains there); detection via GetModuleHandle("libzhl.dll").
 *  - Hooks only ever produce states the engine itself produces:
 *      RenderShadowLayer -> false  ("no shadow layer rendered")
 *      DoGroundImpactEffects -> skipped call while lagging (cosmetic FX)
 *    Measurement hooks call the original unconditionally.
 */

#ifdef _WIN32

#include <windows.h>
#include <stdbool.h>
#include <stdio.h>

#include <MinHook.h>

#include "adaptive.h"
#include "config.h"
#include "sigscan.h"

/* ---------------------------------------------------------------------- */
/* Signatures (REPENTOGON libzhl/functions, Repentance+ v1.9.7.12)        */
/* ---------------------------------------------------------------------- */

#define SIG_RENDER_SHADOW_LAYER \
    "558bec83e4c081ecb4000000f30f1005"
#define SIG_GAME_RENDER \
    "538bdc83ec0883e4f883c404558b6b??896c24??8bec6aff68????????" \
    "64a1????????505381ec20020000"
#define SIG_LEVEL_UPDATE \
    "518b89????????e8"
#define SIG_GROUND_IMPACT_EFFECTS \
    "558bec83e4f881ec9c000000a1????????33c4898424????????a1"

typedef bool(__thiscall *RenderShadowLayer_t)(void *self, void *offset);
typedef void(__thiscall *GameRender_t)(void *self);
typedef void(__thiscall *LevelUpdate_t)(void *self);
/* NOTE: the engine passes the `strength` argument in XMM3 (see the zhl
 * database). We never read or re-source it: on the forward path the value
 * stays in xmm3 untouched, so the original function still receives it. */
typedef void (*GroundImpactEffects_t)(void *pos, void *velocity,
                                      float strength);

static RenderShadowLayer_t g_origShadowLayer = NULL;
static GameRender_t g_origGameRender = NULL;
static LevelUpdate_t g_origLevelUpdate = NULL;
static GroundImpactEffects_t g_origGroundImpact = NULL;

IfpsConfig g_cfg;
IfpsAdaptive g_adaptive;

static int g_effectiveMode = IFPS_SHADOWS_ADAPTIVE;
static int g_groundImpactHooked = 0;
static const char *g_timingSource = "none";
static float g_tickScale = 1.0f;
static volatile LONG g_shadowsSkipped = 0;
static volatile LONG g_impactsSkipped = 0;

extern void ifps_log(const char *fmt, ...);

/* ---------------------------------------------------------------------- */
/* Signature scanning with uniqueness enforcement                          */
/* ---------------------------------------------------------------------- */

/* Returns the address only if the pattern matches EXACTLY once across all
 * executable sections of the main module. 0 matches or >1 matches -> NULL,
 * and the reason is reported through *status ("none" / "ambiguous"). */
static void *scan_unique(const char *pattern, const char **status)
{
    HMODULE mod = GetModuleHandleA(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)mod;
    PIMAGE_NT_HEADERS nt;
    PIMAGE_SECTION_HEADER sec;
    void *found = NULL;
    int matches = 0;
    int i;

    if (status) *status = "none";
    if (!mod || dos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    nt = (PIMAGE_NT_HEADERS)((uint8_t *)mod + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return NULL;

    sec = IMAGE_FIRST_SECTION(nt);
    for (i = 0; i < nt->FileHeader.NumberOfSections && matches < 2; i++) {
        if (sec[i].Characteristics & IMAGE_SCN_MEM_EXECUTE) {
            uint8_t *base = (uint8_t *)mod + sec[i].VirtualAddress;
            size_t len = sec[i].Misc.VirtualSize;
            long off = 0;
            size_t start = 0;
            while (start < len) {
                off = ifps_sigscan(base + start, len - start, pattern);
                if (off < 0) break;
                matches++;
                found = base + start + off;
                if (matches >= 2) break;
                start += (size_t)off + 1;
            }
        }
    }

    if (matches == 1) {
        if (status) *status = "ok";
        return found;
    }
    if (matches > 1 && status) *status = "ambiguous";
    return NULL;
}

/* ---------------------------------------------------------------------- */
/* Detours                                                                 */
/* ---------------------------------------------------------------------- */

static int shedding_now(void)
{
    switch (g_effectiveMode) {
    case IFPS_SHADOWS_ALWAYS:
        return 1;
    case IFPS_SHADOWS_ADAPTIVE:
        return g_adaptive.shadows_off;
    default:
        return 0;
    }
}

static bool __thiscall hkRenderShadowLayer(void *self, void *offset)
{
    if (shedding_now()) {
        InterlockedIncrement(&g_shadowsSkipped);
        return false; /* engine state: "no shadow layer rendered" */
    }
    return g_origShadowLayer(self, offset);
}

/* Cosmetic ground-impact FX (dust/decals on landings and explosions).
 * Skipped only while shedding; otherwise forwarded. See the xmm3 note on
 * the typedef above — this detour must not do float work of its own. */
static void hkGroundImpactEffects(void *pos, void *velocity, float strength)
{
    if (shedding_now()) {
        InterlockedIncrement(&g_impactsSkipped);
        return;
    }
    g_origGroundImpact(pos, velocity, strength);
}

static void feed_sample(double ms)
{
    int before;
    if (ms <= 0.0 || ms >= 5000.0) return;
    before = g_adaptive.shadows_off;
    ifps_adaptive_frame(&g_adaptive, (float)ms);
    if (g_adaptive.shadows_off != before) {
        float est = g_adaptive.ema_ms;
        ifps_log("adaptive: shedding %s (smoothed %.1f ms/frame-equivalent, "
                 "~%.0f fps; %ld samples via %s)",
                 g_adaptive.shadows_off ? "ON (lag detected)" : "OFF (headroom)",
                 est, est > 0.0f ? 1000.0f / est : 0.0f,
                 g_adaptive.frames_seen, g_timingSource);
    }
}

/* Timing source A: Game::Render — one call per rendered frame.
 * Used only when REPENTOGON is absent (it hooks this function itself). */
static void __thiscall hkGameRender(void *self)
{
    static LARGE_INTEGER freq = {{0, 0}};
    static LARGE_INTEGER last = {{0, 0}};
    LARGE_INTEGER now;

    if (freq.QuadPart == 0) QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&now);
    if (last.QuadPart != 0 && freq.QuadPart != 0) {
        feed_sample((double)(now.QuadPart - last.QuadPart) * 1000.0 /
                    (double)freq.QuadPart);
    }
    last = now;
    g_origGameRender(self);
}

/* Timing source B: Level::Update — one call per logic tick (30 Hz) during
 * gameplay. REPENTOGON does not hook it, so it is the measurement source
 * when REPENTOGON is installed. Intervals are scaled by tick_scale (0.5)
 * to 60fps-frame equivalents inside the adaptive controller. */
static void __thiscall hkLevelUpdate(void *self)
{
    static LARGE_INTEGER freq = {{0, 0}};
    static LARGE_INTEGER last = {{0, 0}};
    LARGE_INTEGER now;

    if (freq.QuadPart == 0) QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&now);
    if (last.QuadPart != 0 && freq.QuadPart != 0) {
        feed_sample((double)(now.QuadPart - last.QuadPart) * 1000.0 /
                    (double)freq.QuadPart);
    }
    last = now;
    g_origLevelUpdate(self);
}

/* ---------------------------------------------------------------------- */
/* Install / remove                                                        */
/* ---------------------------------------------------------------------- */

int ifps_repentogon_present(void)
{
    return GetModuleHandleA("libzhl.dll") != NULL ||
           GetModuleHandleA("repentogon.dll") != NULL;
}

static void install_timing_hook(int rg)
{
    const char *status = "none";

    if (!rg) {
        void *p = scan_unique(SIG_GAME_RENDER, &status);
        if (p && MH_CreateHook(p, &hkGameRender,
                               (void **)&g_origGameRender) == MH_OK) {
            g_timingSource = "Game::Render";
            g_tickScale = 1.0f;
            return;
        }
        ifps_log("Game::Render timing unavailable (%s).", status);
    }

    /* REPENTOGON present (or Game::Render failed): use Level::Update. */
    {
        void *p = scan_unique(SIG_LEVEL_UPDATE, &status);
        if (p && MH_CreateHook(p, &hkLevelUpdate,
                               (void **)&g_origLevelUpdate) == MH_OK) {
            g_timingSource = "Level::Update (30Hz ticks)";
            g_tickScale = 0.5f;
            return;
        }
        ifps_log("Level::Update timing unavailable (%s).", status);
    }

    g_timingSource = "none";
}

int ifps_hooks_install(void)
{
    const char *status = "none";
    void *pShadow = NULL, *pImpact = NULL;
    int rg = ifps_repentogon_present();

    g_effectiveMode = g_cfg.shadows_mode;

    ifps_log("REPENTOGON %s.", rg ? "detected" : "not detected");

    if (MH_Initialize() != MH_OK) {
        ifps_log("MH_Initialize failed; no hooks installed.");
        return 0;
    }

    /* Frame measurement first: it decides whether adaptive can work. */
    install_timing_hook(rg);
    if (g_effectiveMode == IFPS_SHADOWS_ADAPTIVE &&
        g_timingSource[0] == 'n' /* "none" */) {
        g_effectiveMode = g_cfg.adaptive_fallback;
        ifps_log("no frame measurement available -> adaptive falls back to "
                 "'%s'. Tip: set shadows=always in isaacfps_native.ini to "
                 "force maximum savings.",
                 g_effectiveMode == IFPS_SHADOWS_ALWAYS ? "always" : "never");
    }

    ifps_adaptive_init(&g_adaptive, g_cfg.target_fps, g_cfg.recover_fps, 30,
                       120, g_tickScale);

    /* Hook 1: entity shadow layers. */
    pShadow = scan_unique(SIG_RENDER_SHADOW_LAYER, &status);
    if (pShadow &&
        MH_CreateHook(pShadow, &hkRenderShadowLayer,
                      (void **)&g_origShadowLayer) == MH_OK) {
        ifps_log("hook: Entity::RenderShadowLayer at %p (mode: %s)", pShadow,
                 g_effectiveMode == IFPS_SHADOWS_ALWAYS    ? "always skip"
                 : g_effectiveMode == IFPS_SHADOWS_ADAPTIVE ? "adaptive"
                                                            : "never skip");
    } else {
        ifps_log("Entity::RenderShadowLayer NOT hooked (%s). Game version "
                 "mismatch? Shadows will not be affected.", status);
        if (!pShadow) {
            /* Without even the shadow hook there is nothing to shed. */
            ifps_log("no hooks installed; the game runs unmodified.");
            MH_Uninitialize();
            return 0;
        }
    }

    /* Hook 2: ground impact FX (optional). */
    if (g_cfg.ground_impacts) {
        pImpact = scan_unique(SIG_GROUND_IMPACT_EFFECTS, &status);
        if (pImpact &&
            MH_CreateHook(pImpact, &hkGroundImpactEffects,
                          (void **)&g_origGroundImpact) == MH_OK) {
            g_groundImpactHooked = 1;
            ifps_log("hook: Entity::DoGroundImpactEffects at %p", pImpact);
        } else {
            ifps_log("Entity::DoGroundImpactEffects NOT hooked (%s); "
                     "continuing without it.", status);
        }
    }

    if (MH_EnableHook(MH_ALL_HOOKS) != MH_OK) {
        ifps_log("MH_EnableHook failed; no hooks active.");
        MH_Uninitialize();
        return 0;
    }

    ifps_log("active: timing=%s, shadows=%s%s | target %.0f fps / recover "
             "%.0f fps",
             g_timingSource,
             g_effectiveMode == IFPS_SHADOWS_ALWAYS    ? "always"
             : g_effectiveMode == IFPS_SHADOWS_ADAPTIVE ? "adaptive"
                                                        : "never",
             g_groundImpactHooked ? ", ground-impacts=adaptive" : "",
             g_cfg.target_fps, g_cfg.recover_fps);
    return 1;
}

void ifps_hooks_remove(void)
{
    MH_DisableHook(MH_ALL_HOOKS);
    MH_Uninitialize();
    ifps_log("hooks removed | shadows skipped: %ld | ground impacts "
             "skipped: %ld | samples seen: %ld",
             (long)g_shadowsSkipped, (long)g_impactsSkipped,
             g_adaptive.frames_seen);
}

#endif /* _WIN32 */
