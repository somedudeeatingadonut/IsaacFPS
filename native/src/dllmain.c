/* IsaacFPS native :: DLL entry point.
 *
 * Safety interlocks, in order:
 *   1. If a file named isaacfps_native.off exists next to this DLL, it does
 *      nothing at all (kill switch).
 *   2. If enabled=0 in isaacfps_native.ini, it does nothing.
 *   3. Every function it touches must be found by signature first; on any
 *      mismatch (e.g. the game updated) it installs no hooks and the game
 *      runs completely unmodified.
 */

#ifdef _WIN32

#include <windows.h>
#include <stdarg.h>
#include <stdio.h>

#include "config.h"

extern IfpsConfig g_cfg;
extern int ifps_hooks_install(void);
extern void ifps_hooks_remove(void);

#define IFPS_NATIVE_VERSION "1.0.0"

static FILE *g_logFile = NULL;
static char g_dir[MAX_PATH] = "";
static int g_hooked = 0;

void ifps_log(const char *fmt, ...)
{
    va_list ap;
    if (!g_logFile) return;
    va_start(ap, fmt);
    fprintf(g_logFile, "[IsaacFPS-native] ");
    vfprintf(g_logFile, fmt, ap);
    fprintf(g_logFile, "\n");
    fflush(g_logFile);
    va_end(ap);
}

static void get_dll_dir(HMODULE self)
{
    char path[MAX_PATH];
    char *slash;
    GetModuleFileNameA(self, path, MAX_PATH);
    path[MAX_PATH - 1] = '\0';
    slash = strrchr(path, '\\');
    if (slash) *slash = '\0';
    strncpy(g_dir, path, MAX_PATH - 1);
    g_dir[MAX_PATH - 1] = '\0';
}

static int file_exists(const char *dir, const char *name)
{
    char path[MAX_PATH];
    DWORD attr;
    _snprintf(path, MAX_PATH, "%s\\%s", dir, name);
    attr = GetFileAttributesA(path);
    return attr != INVALID_FILE_ATTRIBUTES &&
           !(attr & FILE_ATTRIBUTE_DIRECTORY);
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved)
{
    (void)reserved;

    switch (reason) {
    case DLL_PROCESS_ATTACH: {
        char cfgPath[MAX_PATH];
        char logPath[MAX_PATH];

        DisableThreadLibraryCalls(hinst);
        get_dll_dir(hinst);

        /* 1) kill switch */
        if (file_exists(g_dir, "isaacfps_native.off")) return TRUE;

        ifps_config_defaults(&g_cfg);
        _snprintf(cfgPath, MAX_PATH, "%s\\isaacfps_native.ini", g_dir);
        ifps_config_load_file(&g_cfg, cfgPath);

        if (g_cfg.log) {
            _snprintf(logPath, MAX_PATH, "%s\\isaacfps_native.log", g_dir);
            g_logFile = fopen(logPath, "a");
        }

        ifps_log("v%s attached to pid %lu", IFPS_NATIVE_VERSION,
                 GetCurrentProcessId());

        /* 2) master switch */
        if (!g_cfg.enabled) {
            ifps_log("disabled by config (enabled=0); doing nothing.");
            return TRUE;
        }

        /* 3) signature-verified hooks only */
        g_hooked = ifps_hooks_install();
        if (!g_hooked) {
            ifps_log("no hooks installed; the game is running unmodified.");
        }
        return TRUE;
    }

    case DLL_PROCESS_DETACH:
        if (g_hooked) ifps_hooks_remove();
        ifps_log("detached.");
        if (g_logFile) fclose(g_logFile);
        return TRUE;

    default:
        return TRUE;
    }
}

#endif /* _WIN32 */
