#!/usr/bin/env python3
"""IsaacFPS Booster — external (non-mod) performance toolkit.

Works OUTSIDE the game's mod framework: it tunes Isaac's engine configuration
(options.ini) and, on Windows, the game process itself. Nothing here injects
or patches game code, so there is zero crash/save-corruption risk; every file
edit is backed up first and can be restored.

Commands
--------
  scan                     find Isaac save folders + show current options
  profile NAME [--vsync off|keep] [--dry-run]
                           apply a performance profile to options.ini
                           (balanced | performance | potato)
  restore                  restore the latest options.ini backup
  tune [--priority high|normal] [--affinity MASK] [--dry-run]
                           (Windows only) tune the running isaac-ng.exe
                           process: priority class, CPU affinity, power
                           throttling opt-out
  report                   print the native-lever checklist (REPENTOGON
                           features + engine options + driver settings)

Why these levers? See docs/NATIVE_PATH.md in this repository: they come from
REPENTOGON's own C++ source (engine option fields) and from the engine's
documented options.ini keys.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# options.ini handling (format-preserving INI editor)
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(r"^\s*\[(.+?)\]\s*$")
KEY_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")


class IniDoc:
    """Minimal INI editor that preserves file layout.

    Keeps every original line; set() replaces the value in place, or appends
    the key to the section (or the section to the file) when missing.
    """

    def __init__(self, lines: List[str]):
        self.lines = lines

    @classmethod
    def parse(cls, text: str) -> "IniDoc":
        return cls(text.splitlines())

    def get(self, section: str, key: str) -> Optional[str]:
        in_section = False
        for line in self.lines:
            m = SECTION_RE.match(line)
            if m:
                in_section = (m.group(1).strip().lower() == section.lower())
                continue
            if in_section:
                km = KEY_RE.match(line)
                if km and km.group(1).lower() == key.lower():
                    return km.group(2)
        return None

    def set(self, section: str, key: str, value: str) -> str:
        """Set key=value in [section]. Returns 'changed', 'unchanged' or 'added'."""
        in_section = False
        section_start = -1
        for i, line in enumerate(self.lines):
            m = SECTION_RE.match(line)
            if m:
                if in_section:
                    break  # passed the target section without finding the key
                in_section = (m.group(1).strip().lower() == section.lower())
                if in_section:
                    section_start = i
                continue
            if in_section:
                km = KEY_RE.match(line)
                if km and km.group(1).lower() == key.lower():
                    old = km.group(2)
                    if old == str(value):
                        return "unchanged"
                    self.lines[i] = f"{km.group(1)}={value}"
                    return "changed"
        if section_start == -1:
            if self.lines and self.lines[-1].strip() != "":
                self.lines.append("")
            self.lines.append(f"[{section}]")
            section_start = len(self.lines) - 1
        self.lines.insert(section_start + 1, f"{key}={value}")
        return "added"

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def load_ini(path: str) -> IniDoc:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return IniDoc.parse(fh.read())


# ---------------------------------------------------------------------------
# Performance profiles
# ---------------------------------------------------------------------------
# Keys verified against REPENTOGON's C++ source (OptionsConfig fields in
# repentogon/ImGuiFeatures/GameOptions.h) and community-documented
# options.ini usage. Effect toggles trade visual atmosphere for GPU/CPU time.

PROFILES: Dict[str, Dict[str, str]] = {
    # Safe defaults: cuts the biggest hidden costs without touching visuals.
    "balanced": {
        "MaxRenderScale": "2",       # cap internal render scale (Rep+ default is 3)
        "ControllerHotplug": "0",    # stop constant USB controller scanning
    },
    # Adds engine effect toggles that cost GPU fill/overdraw.
    "performance": {
        "MaxRenderScale": "1",       # lowest internal render scale
        "ControllerHotplug": "0",
        "EnableColorCorrection": "0",
        "EnableShockwave": "0",
        "EnableCaustics": "0",
        "EnableBloom": "0",
        "EnableWaterSurface": "0",
    },
    # Everything off that can go off. Ugly, fast.
    "potato": {
        "MaxRenderScale": "1",
        "ControllerHotplug": "0",
        "EnableColorCorrection": "0",
        "EnableShockwave": "0",
        "EnableCaustics": "0",
        "EnableBloom": "0",
        "EnableWaterSurface": "0",
        "EnableLighting": "0",
        "EnableFilter": "0",
        "EnableInterpolation": "0",
    },
}


@dataclass
class Tuning:
    changes: List[Tuple[str, str, str]] = field(default_factory=list)  # (key, old, new)
    path: str = ""
    backup: str = ""


# ---------------------------------------------------------------------------
# Isaac install discovery
# ---------------------------------------------------------------------------

SAVE_DIR_NAMES = (
    "Binding of Isaac Repentance+",
    "Binding of Isaac Repentance",
)


def find_save_dirs() -> List[str]:
    docs = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    base = os.path.join(docs, "Documents", "My Games")
    out = []
    for name in SAVE_DIR_NAMES:
        p = os.path.join(base, name)
        if os.path.isdir(p):
            out.append(p)
    # Also honor an explicit override.
    env = os.environ.get("ISAAC_SAVE_DIR")
    if env and os.path.isdir(env) and env not in out:
        out.insert(0, env)
    return out


def find_options_files() -> List[str]:
    out = []
    for d in find_save_dirs():
        p = os.path.join(d, "options.ini")
        if os.path.isfile(p):
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Profile application
# ---------------------------------------------------------------------------

def backup_once(path: str) -> str:
    backup = path + ".isaacfps.bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    return backup


def apply_profile(path: str, profile: str, vsync: str = "keep",
                  dry_run: bool = False) -> Tuning:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile '{profile}' (choose from: "
                         + ", ".join(PROFILES) + ")")
    doc = load_ini(path)
    t = Tuning(path=path)

    plan = dict(PROFILES[profile])
    if vsync == "off":
        plan["VSync"] = "0"
    elif vsync == "on":
        plan["VSync"] = "1"

    for key, value in plan.items():
        old = doc.get("Options", key)
        if old == value:
            continue
        t.changes.append((key, old if old is not None else "<unset>", value))
        if not dry_run:
            doc.set("Options", key, value)

    if not dry_run and t.changes:
        t.backup = backup_once(path)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc.text())
    return t


def restore(path: str) -> Optional[str]:
    backup = path + ".isaacfps.bak"
    if not os.path.exists(backup):
        return None
    shutil.copy2(backup, path)
    return backup


# ---------------------------------------------------------------------------
# Windows process tuning (no injection - only documented Win32 process APIs)
# ---------------------------------------------------------------------------

PROCESS_NAME = "isaac-ng.exe"
HIGH_PRIORITY_CLASS = 0x00000080
NORMAL_PRIORITY_CLASS = 0x00000020
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_INFORMATION = 0x0200
TH32CS_SNAPPROCESS = 0x00000002


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_char * 260),
    ]


@dataclass
class TuneResult:
    pid: int = 0
    priority_before: str = "?"
    priority_after: str = "?"
    affinity_before: str = "?"
    affinity_after: str = "?"
    throttling_optout: bool = False


def _find_isaac_pids(kernel32) -> List[int]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return []
    pids = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        ok = kernel32.Process32First(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile.decode("ascii", "ignore").lower()
            if name == PROCESS_NAME:
                pids.append(entry.th32ProcessID)
            ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return pids


def tune_process(pid: int, priority: str = "high",
                 affinity: Optional[int] = None,
                 kernel32=None) -> TuneResult:
    """Tune one isaac-ng.exe process. kernel32 is injectable for tests."""
    if kernel32 is None:  # pragma: no cover - windows only
        kernel32 = ctypes.windll.kernel32

    res = TuneResult(pid=pid)
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_INFORMATION, False, pid)
    if not handle:
        raise RuntimeError(f"could not open process {pid} (error "
                           f"{kernel32.GetLastError()}); run as the same user.")

    try:
        cls = kernel32.GetPriorityClass(handle)
        res.priority_before = ("high" if cls == HIGH_PRIORITY_CLASS else
                               "normal" if cls == NORMAL_PRIORITY_CLASS else str(cls))

        want = HIGH_PRIORITY_CLASS if priority == "high" else NORMAL_PRIORITY_CLASS
        if kernel32.SetPriorityClass(handle, want):
            res.priority_after = priority
        else:
            res.priority_after = res.priority_before

        if affinity is not None:
            mask = ctypes.c_size_t(0)
            if kernel32.GetProcessAffinityMask(handle, ctypes.byref(mask),
                                               ctypes.byref(ctypes.c_size_t())):
                res.affinity_before = hex(mask.value)
            if kernel32.SetProcessAffinityMask(handle, affinity):
                res.affinity_after = hex(affinity)

        # Opt the process out of Windows power throttling (the same API
        # REPENTOGON's eco mode uses, applied in reverse).
        class PowerThrottling(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_ulong),
                        ("ControlMask", ctypes.c_ulong),
                        ("StateMask", ctypes.c_ulong)]
        try:  # pragma: no cover - windows only
            setter = kernel32.SetProcessInformation
            try:
                setter.restype = ctypes.c_int  # real ctypes function object
            except (AttributeError, TypeError):
                pass  # plain callable (e.g. test fake)
            pt = PowerThrottling(Version=1, ControlMask=1, StateMask=0)
            res.throttling_optout = bool(
                setter(handle, 2, ctypes.byref(pt), ctypes.sizeof(pt)))
        except Exception:
            res.throttling_optout = False
    finally:
        kernel32.CloseHandle(handle)
    return res


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

REPORT = """
=== IsaacFPS native-lever checklist ===

1) MEASURE first (know what you are fixing):
   - In game: IsaacFPS overlay + fpsreport() (frame spikes with stage/entities).
   - With REPENTOGON: its debug bar (~ key) has a log viewer and game options.

2) REPENTOGON native features (its ImGui menu, '~' key -> REPENTOGON):
   - "Fast lasers"   : native hook that tracks lag and cuts laser sample counts
                       when the game drops frames (repentogon/Patches/LagMetric.cpp)
   - "Quick room clear" : skips room-clear delay padding
   - "Eco mode"      : idles the process when minimized (saves heat, no in-game cost)
   - Generational GC : already on by default (Lua 5.4 swap done by its loader)

3) Engine options (options.ini [Options]; this tool automates them):
   - MaxRenderScale=1 or 2   : biggest single GPU lever on high-DPI screens
                               (Repentance+ defaults to 3)
   - ControllerHotplug=0     : stops constant USB controller scanning
   - VSync=0 + cap FPS in your GPU driver panel (NVIDIA/AMD) or RTSS:
                               uncapped Isaac wastes CPU rendering 1000fps menus
   - Effect toggles when GPU-bound: EnableColorCorrection, EnableShockwave,
     EnableCaustics, EnableBloom, EnableWaterSurface, EnableLighting, EnableFilter

4) OS level (this tool's 'tune' command on Windows):
   - HIGH priority for isaac-ng.exe
   - CPU affinity: on hybrid Intel CPUs (12th gen+), pin Isaac to P-cores
     (e.g. --affinity 0xFF for cores 0-7); old 32-bit game code often gets
     scheduled onto E-cores and loses ~30-40%
   - Power throttling opt-out

5) MOD collection hygiene (this is usually the real 40->60 blocker):
   - fpsreport() spikes always in the same rooms -> one mod's spawns/callbacks
   - Migrate heavy overlay mods to IsaacFPS.AddRender(fn, N) (every Nth frame)
   - REPENTOGON's callback error isolation stops one broken mod from dragging
     every other mod's callbacks down with it

If all of the above is done and heavy rooms still lag, the remaining ceiling
is inside the game's C++ renderer itself; the responsible path for that is
contributing a hook to REPENTOGON (open source), not a blind injector.
See docs/NATIVE_PATH.md for the full technical breakdown.
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_scan(_args) -> int:
    dirs = find_save_dirs()
    if not dirs:
        print("No Isaac save folder found. Set ISAAC_SAVE_DIR to override.")
        return 1
    for d in dirs:
        print(f"save folder: {d}")
        ini = os.path.join(d, "options.ini")
        if not os.path.isfile(ini):
            print("  (no options.ini yet - launch the game once)")
            continue
        doc = load_ini(ini)
        interesting = ["VSync", "MaxRenderScale", "ControllerHotplug",
                       "EnableLighting", "EnableColorCorrection",
                       "EnableShockwave", "EnableCaustics", "EnableBloom",
                       "EnableWaterSurface", "EnableFilter", "EnableInterpolation"]
        for k in interesting:
            v = doc.get("Options", k)
            print(f"  {k} = {v if v is not None else '<unset>'}")
    return 0


def cmd_profile(args) -> int:
    files = find_options_files()
    if not files:
        print("No options.ini found (run 'scan'; launch the game once to create it).")
        return 1
    for path in files:
        t = apply_profile(path, args.profile, vsync=args.vsync, dry_run=args.dry_run)
        print(f"[{('DRY RUN - ' if args.dry_run else '')}{path}] profile '{args.profile}'")
        if not t.changes:
            print("  nothing to change")
            continue
        for key, old, new in t.changes:
            print(f"  {key}: {old} -> {new}")
        if not args.dry_run:
            print(f"  backup: {t.backup}")
    print("Relaunch the game to apply.")
    return 0


def cmd_restore(_args) -> int:
    files = find_options_files()
    did = False
    for path in files:
        b = restore(path)
        if b:
            print(f"restored {path} from {b}")
            did = True
    if not did:
        print("no backups found (nothing to restore)")
    return 0 if did else 1


def cmd_tune(args) -> int:
    if sys.platform != "win32" or not hasattr(ctypes, "windll"):
        print("'tune' only works on Windows (the game only runs there).")
        return 1
    kernel32 = ctypes.windll.kernel32  # pragma: no cover
    pids = _find_isaac_pids(kernel32)  # pragma: no cover
    if not pids:
        print(f"{PROCESS_NAME} is not running.")
        return 1
    for pid in pids:  # pragma: no cover
        if args.dry_run:
            print(f"[DRY RUN] would tune pid {pid}")
            continue
        r = tune_process(pid, priority=args.priority, affinity=args.affinity,
                         kernel32=kernel32)
        print(f"pid {r.pid}: priority {r.priority_before} -> {r.priority_after}; "
              f"affinity {r.affinity_before} -> {r.affinity_after}; "
              f"throttling opt-out: {r.throttling_optout}")
    return 0


def cmd_report(_args) -> int:
    print(REPORT)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="isaacfps_booster",
                                description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="find Isaac folders and show current options")

    pr = sub.add_parser("profile", help="apply a performance profile to options.ini")
    pr.add_argument("profile", choices=sorted(PROFILES))
    pr.add_argument("--vsync", choices=("keep", "off", "on"), default="keep")
    pr.add_argument("--dry-run", action="store_true")

    sub.add_parser("restore", help="restore the latest options.ini backup")

    tu = sub.add_parser("tune", help="tune the running isaac-ng.exe (Windows)")
    tu.add_argument("--priority", choices=("high", "normal"), default="high")
    tu.add_argument("--affinity", type=lambda s: int(s, 0), default=None,
                    help="CPU affinity mask, e.g. 0xFF for cores 0-7")
    tu.add_argument("--dry-run", action="store_true")

    sub.add_parser("report", help="print the native-lever checklist")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "scan": cmd_scan,
        "profile": cmd_profile,
        "restore": cmd_restore,
        "tune": cmd_tune,
        "report": cmd_report,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
