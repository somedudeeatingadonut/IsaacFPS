/* IsaacFPS native :: injector.
 *
 * Loads isaacfps_native.dll into a running isaac-ng.exe process using the
 * classic CreateRemoteThread + LoadLibraryA technique (the same family of
 * mechanism REPENTOGON's loader uses via libs/injector). No game files are
 * modified; ejecting the DLL restores the process to its original code.
 *
 * Usage:
 *   isaacfps_injector.exe                 inject (default DLL path)
 *   isaacfps_injector.exe --dll my.dll    inject a specific DLL
 *   isaacfps_injector.exe --eject         unload it again
 *   isaacfps_injector.exe --list          show Isaac processes
 */

#ifdef _WIN32

#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>

#define TARGET_PROCESS "isaac-ng.exe"
#define DLL_NAME "isaacfps_native.dll"

static int find_process_ids(DWORD *pids, int max)
{
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32 pe;
    int n = 0;

    if (snap == INVALID_HANDLE_VALUE) return 0;
    pe.dwSize = sizeof(pe);
    if (Process32First(snap, &pe)) {
        do {
            if (_stricmp(pe.szExeFile, TARGET_PROCESS) == 0 && n < max)
                pids[n++] = pe.th32ProcessID;
        } while (Process32Next(snap, &pe));
    }
    CloseHandle(snap);
    return n;
}

static HMODULE find_module_in_process(DWORD pid, const char *name)
{
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE |
                                               TH32CS_SNAPMODULE32,
                                           pid);
    MODULEENTRY32 me;
    HMODULE found = NULL;

    if (snap == INVALID_HANDLE_VALUE) return NULL;
    me.dwSize = sizeof(me);
    if (Module32First(snap, &me)) {
        do {
            if (_stricmp(me.szModule, name) == 0) {
                found = me.hModule;
                break;
            }
        } while (Module32Next(snap, &me));
    }
    CloseHandle(snap);
    return found;
}

static int inject(DWORD pid, const char *dllPath)
{
    HANDLE proc, thread;
    void *remote;
    size_t len = strlen(dllPath) + 1;
    DWORD exitCode = 0;

    proc = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_WRITE |
                           PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION,
                       FALSE, pid);
    if (!proc) {
        printf("error: cannot open pid %lu (error %lu).\n", pid,
               GetLastError());
        return 1;
    }

    remote = VirtualAllocEx(proc, NULL, len, MEM_COMMIT | MEM_RESERVE,
                            PAGE_READWRITE);
    if (!remote) {
        printf("error: VirtualAllocEx failed (%lu).\n", GetLastError());
        CloseHandle(proc);
        return 1;
    }
    if (!WriteProcessMemory(proc, remote, dllPath, len, NULL)) {
        printf("error: WriteProcessMemory failed (%lu).\n", GetLastError());
        VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
        CloseHandle(proc);
        return 1;
    }

    thread = CreateRemoteThread(proc, NULL, 0,
                                (LPTHREAD_START_ROUTINE)LoadLibraryA, remote,
                                0, NULL);
    if (!thread) {
        printf("error: CreateRemoteThread failed (%lu).\n", GetLastError());
        VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
        CloseHandle(proc);
        return 1;
    }

    WaitForSingleObject(thread, 10000);
    GetExitCodeThread(thread, &exitCode);

    VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
    CloseHandle(thread);
    CloseHandle(proc);

    if (exitCode == 0) {
        printf("error: the DLL failed to load into pid %lu.\n", pid);
        return 1;
    }
    printf("injected %s into pid %lu (module base 0x%08lX).\n", dllPath, pid,
           exitCode);
    printf("check isaacfps_native.log next to the DLL for hook status.\n");
    return 0;
}

static int eject(DWORD pid, const char *dllName)
{
    HANDLE proc, thread;
    HMODULE mod = find_module_in_process(pid, dllName);
    DWORD exitCode = 0;

    if (!mod) {
        printf("%s is not loaded in pid %lu.\n", dllName, pid);
        return 1;
    }
    proc = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION,
                       FALSE, pid);
    if (!proc) {
        printf("error: cannot open pid %lu (error %lu).\n", pid,
               GetLastError());
        return 1;
    }
    thread = CreateRemoteThread(proc, NULL, 0,
                                (LPTHREAD_START_ROUTINE)FreeLibrary, mod, 0,
                                NULL);
    if (!thread) {
        printf("error: CreateRemoteThread failed (%lu).\n", GetLastError());
        CloseHandle(proc);
        return 1;
    }
    WaitForSingleObject(thread, 10000);
    GetExitCodeThread(thread, &exitCode);
    CloseHandle(thread);
    CloseHandle(proc);
    if (exitCode) {
        printf("ejected %s from pid %lu. Game code restored.\n", dllName,
               pid);
        return 0;
    }
    printf("eject may have failed for pid %lu.\n", pid);
    return 1;
}

int main(int argc, char **argv)
{
    DWORD pids[8];
    int n, i;
    const char *dllPath = NULL;
    char resolved[MAX_PATH];
    int doEject = 0, doList = 0;

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--dll") == 0 && i + 1 < argc)
            dllPath = argv[++i];
        else if (strcmp(argv[i], "--eject") == 0)
            doEject = 1;
        else if (strcmp(argv[i], "--list") == 0)
            doList = 1;
    }

    if (!dllPath) {
        char dir[MAX_PATH];
        char *slash;
        GetModuleFileNameA(NULL, dir, MAX_PATH);
        slash = strrchr(dir, '\\');
        if (slash) *(slash + 1) = '\0';
        _snprintf(resolved, MAX_PATH, "%s%s", dir, DLL_NAME);
        dllPath = resolved;
    }

    n = find_process_ids(pids, 8);
    if (doList) {
        if (n == 0) printf("%s is not running.\n", TARGET_PROCESS);
        for (i = 0; i < n; i++) printf("pid %lu\n", pids[i]);
        return n ? 0 : 1;
    }
    if (n == 0) {
        printf("%s is not running - start the game first.\n", TARGET_PROCESS);
        return 1;
    }

    for (i = 0; i < n; i++) {
        if (doEject) {
            if (eject(pids[i], DLL_NAME)) return 1;
        } else {
            if (inject(pids[i], dllPath)) return 1;
        }
    }
    return 0;
}

#endif /* _WIN32 */
