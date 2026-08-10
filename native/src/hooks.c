/* IsaacFPS native :: game hooks (Windows only).
 *
 * Mechanism: same approach REPENTOGON uses (libzhl) — locate functions in
 * isaac-ng.exe by byte signature, then install inline detours. Signatures
 * below are taken from REPENTOGON's open symbol database (the .zhl files
 * under libzhl/functions) which matches Repentance+ v1.9.7.12.
 *
 * Hook 1: Entity::RenderShadowLayer(Vector*) -> bool
 *   Entity shadows are drawn for every enemy, tear, projectile and pickup.
 *   In tear-heavy synergy rooms that is thousands of extra shadow renders
 *   per frame. Skipping the layer is a plain "return false" — a state the
 *   engine itself produces when an entity has no shadow — so it is one of
 *   the safest possible render hooks.
 *
 * Hook 2: Game::Render() -> void  (measurement only)
 *   Feeds frame times to the adaptive controller. Only installed when
 *   REPENTOGON is NOT present (REPENTOGON already hooks Game::Render, and
 *   two independent inline hooks on one function should not be stacked).
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

typedef bool(__thiscall *RenderShadowLayer_t)(void *self, void *offset);
typedef void(__thiscall *GameRender_t)(void *self);

static RenderShadowLayer_t g_origShadowLayer = NULL;
static GameRender_t g_origGameRender = NULL;

IfpsConfig g_cfg;
IfpsAdaptive g_adaptive;
static int g_effectiveMode = IFPS_SHADOWS_ADAPTIVE;
static volatile LONG g_shadowsSkipped = 0;
static int g_lastDecision = 0;

extern void ifps_log(const char *fmt, ...);

/* ---------------------------------------------------------------------- */
/* Signature scanning of the main module                                   */
/* ---------------------------------------------------------------------- */

static void *scan_main_module(const char *pattern)
{
    HMODULE mod = GetModuleHandleA(NULL);
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)mod;
    PIMAGE_NT_HEADERS nt;
    PIMAGE_SECTION_HEADER sec;
    int i;

    if (!mod || dos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    nt = (PIMAGE_NT_HEADERS)((uint8_t *)mod + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return NULL;

    sec = IMAGE_FIRST_SECTION(nt);
    for (i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (sec[i].Characteristics & IMAGE_SCN_MEM_EXECUTE) {
            uint8_t *base = (uint8_t *)mod + sec[i].VirtualAddress;
            size_t len = sec[i].Misc.VirtualSize;
            long off = ifps_sigscan(base, len, pattern);
            if (off >= 0) return base + off;
        }
    }
    return NULL;
}

/* ---------------------------------------------------------------------- */
/* Detours                                                                 */
/* ---------------------------------------------------------------------- */

static bool __thiscall hkRenderShadowLayer(void *self, void *offset)
{
    int skip = 0;

    switch (g_effectiveMode) {
    case IFPS_SHADOWS_ALWAYS:
        skip = 1;
        break;
    case IFPS_SHADOWS_ADAPTIVE:
        skip = g_adaptive.shadows_off;
        break;
    default:
        skip = 0;
        break;
    }

    if (skip) {
        InterlockedIncrement(&g_shadowsSkipped);
        return false; /* engine treats this as "no shadow layer rendered" */
    }
    return g_origShadowLayer(self, offset);
}

static void __thiscall hkGameRender(void *self)
{
    static LARGE_INTEGER freq = {{0, 0}};
    static LARGE_INTEGER last = {{0, 0}};
    LARGE_INTEGER now;

    if (freq.QuadPart == 0) QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&now);

    if (last.QuadPart != 0 && freq.QuadPart != 0) {
        double ms = (double)(now.QuadPart - last.QuadPart) * 1000.0 /
                    (double)freq.QuadPart;
        if (ms > 0.0 && ms < 5000.0) {
            int before = g_adaptive.shadows_off;
            ifps_adaptive_frame(&g_adaptive, (float)ms);
            if (g_adaptive.shadows_off != before) {
                ifps_log("adaptive: shadows %s (ema %.1f ms, ~%.0f fps; %ld frames measured)",
                         g_adaptive.shadows_off ? "OFF (lag detected)" : "back ON",
                         g_adaptive.ema_ms, 1000.0 / g_adaptive.ema_ms,
                         g_adaptive.frames_seen);
            }
        }
    }
    last = now;

    g_origGameRender(self);
}

/* ---------------------------------------------------------------------- */
/* Install / remove                                                        */
/* ---------------------------------------------------------------------- */

int ifps_repentogon_present(void)
{
    return GetModuleHandleA("libzhl.dll") != NULL ||
           GetModuleHandleA("repentogon.dll") != NULL;
}

int ifps_hooks_install(void)
{
    void *pShadow = NULL, *pRender = NULL;
    int rg = ifps_repentogon_present();
    int needRender = 0;

    g_effectiveMode = g_cfg.shadows_mode;
    if (g_effectiveMode == IFPS_SHADOWS_ADAPTIVE && rg) {
        g_effectiveMode = g_cfg.adaptive_fallback;
        ifps_log("REPENTOGON detected: it already hooks Game::Render, so frame "
                 "measurement is unavailable; adaptive mode falls back to '%s'.",
                 g_effectiveMode == IFPS_SHADOWS_ALWAYS ? "always" : "never");
    }
    needRender = (g_effectiveMode == IFPS_SHADOWS_ADAPTIVE);

    pShadow = scan_main_module(SIG_RENDER_SHADOW_LAYER);
    if (!pShadow) {
        ifps_log("signature for Entity::RenderShadowLayer not found - game "
                 "version mismatch? NO hooks installed; game runs unmodified.");
        return 0;
    }
    if (needRender) {
        pRender = scan_main_module(SIG_GAME_RENDER);
        if (!pRender) {
            ifps_log("signature for Game::Render not found - falling back to "
                     "'never' instead of adaptive.");
            g_effectiveMode = g_cfg.adaptive_fallback;
            needRender = 0;
        }
    }

    ifps_adaptive_init(&g_adaptive, g_cfg.target_fps, g_cfg.recover_fps, 30, 120);

    if (MH_Initialize() != MH_OK) {
        ifps_log("MH_Initialize failed; no hooks installed.");
        return 0;
    }
    if (MH_CreateHook(pShadow, &hkRenderShadowLayer,
                      (void **)&g_origShadowLayer) != MH_OK) {
        ifps_log("failed to hook Entity::RenderShadowLayer; aborted.");
        MH_Uninitialize();
        return 0;
    }
    if (needRender &&
        MH_CreateHook(pRender, &hkGameRender, (void **)&g_origGameRender) !=
            MH_OK) {
        ifps_log("failed to hook Game::Render; continuing without measurement.");
        g_effectiveMode = g_cfg.adaptive_fallback;
    }
    if (MH_EnableHook(MH_ALL_HOOKS) != MH_OK) {
        ifps_log("MH_EnableHook failed; no hooks active.");
        MH_Uninitialize();
        return 0;
    }

    ifps_log("hooks active: RenderShadowLayer=%p (mode: %s)%s",
             pShadow,
             g_effectiveMode == IFPS_SHADOWS_ALWAYS    ? "always skip"
             : g_effectiveMode == IFPS_SHADOWS_ADAPTIVE ? "adaptive"
                                                        : "never skip",
             needRender ? " + Game::Render measurement" : "");
    return 1;
}

void ifps_hooks_remove(void)
{
    MH_DisableHook(MH_ALL_HOOKS);
    MH_Uninitialize();
    ifps_log("hooks removed (shadows skipped this session: %ld).",
             (long)g_shadowsSkipped);
}

#endif /* _WIN32 */
