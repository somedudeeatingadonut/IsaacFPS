#!/usr/bin/env python3
"""Tests for isaacfps_booster.py. Runs anywhere (Win32 tuning is exercised
through an injected fake kernel32)."""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import isaacfps_booster as B  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f" FAIL {name} {extra}")


SAMPLE_INI = """[Options]
MusicVolume=0.8
VSync=1
MaxRenderScale=3
SomethingElse=keepme

[Other]
Foo=1
"""


def test_ini():
    print("== IniDoc ==")
    doc = B.IniDoc.parse(SAMPLE_INI)
    check("get existing", doc.get("Options", "VSync") == "1")
    check("get case-insensitive section", doc.get("options", "vsync") == "1")
    check("get missing returns None", doc.get("Options", "Nope") is None)

    r = doc.set("Options", "VSync", "0")
    check("set changes in place", r == "changed" and doc.get("Options", "VSync") == "0")
    check("layout preserved around edit",
          "MusicVolume=0.8" in doc.text() and "SomethingElse=keepme" in doc.text())

    r = doc.set("Options", "VSync", "0")
    check("idempotent set reports unchanged", r == "unchanged")

    r = doc.set("Options", "ControllerHotplug", "0")
    check("new key added to section",
          r == "added" and doc.get("Options", "ControllerHotplug") == "0")

    r = doc.set("Brand", "Key", "7")
    check("new section created", r == "added" and doc.get("Brand", "Key") == "7")

    check("other sections untouched", doc.get("Other", "Foo") == "1")


def test_profiles(tmp):
    print("== profiles ==")
    ini = os.path.join(tmp, "options.ini")
    with open(ini, "w") as f:
        f.write(SAMPLE_INI)

    t = B.apply_profile(ini, "balanced", dry_run=True)
    check("dry run lists changes", len(t.changes) >= 2)
    with open(ini) as f:
        check("dry run does not write", "MaxRenderScale=3" in f.read())

    t = B.apply_profile(ini, "balanced")
    check("backup created", os.path.exists(ini + ".isaacfps.bak"))
    doc = B.load_ini(ini)
    check("MaxRenderScale lowered", doc.get("Options", "MaxRenderScale") == "2")
    check("ControllerHotplug disabled", doc.get("Options", "ControllerHotplug") == "0")
    check("unrelated keys untouched", doc.get("Options", "MusicVolume") == "0.8")

    b = B.apply_profile(ini, "balanced")
    check("second apply is a no-op", b.changes == [])

    B.apply_profile(ini, "performance", vsync="off")
    doc = B.load_ini(ini)
    check("performance profile effects",
          doc.get("Options", "MaxRenderScale") == "1" and
          doc.get("Options", "EnableShockwave") == "0")
    check("vsync off applied", doc.get("Options", "VSync") == "0")

    restored = B.restore(ini)
    check("restore works", restored is not None)
    doc = B.load_ini(ini)
    check("restored original values", doc.get("Options", "MaxRenderScale") == "3")

    try:
        B.apply_profile(ini, "nope")
        check("unknown profile rejected", False)
    except ValueError:
        check("unknown profile rejected", True)


class FakeKernel32:
    """Just enough of kernel32 for tune_process()."""

    def __init__(self):
        self.priority = B.NORMAL_PRIORITY_CLASS
        self.affinity = 0xFF
        self.throttling_calls = []
        self.closed = 0

    def OpenProcess(self, *a):
        return 0x1234

    def GetLastError(self):
        return 0

    def GetPriorityClass(self, h):
        return self.priority

    def SetPriorityClass(self, h, cls):
        self.priority = cls
        return 1

    def GetProcessAffinityMask(self, h, out_mask, out_sys):
        out_mask._obj.value = self.affinity if hasattr(out_mask, "_obj") else self.affinity
        try:
            out_mask[0] = self.affinity
        except Exception:
            pass
        return 1

    def SetProcessAffinityMask(self, h, mask):
        self.affinity = mask
        return 1

    def SetProcessInformation(self, h, cls, data, size):
        self.throttling_calls.append((cls, size))
        return 1

    def CloseHandle(self, h):
        self.closed += 1
        return 1


def test_tune():
    print("== process tuning (fake kernel32) ==")
    k = FakeKernel32()
    r = B.tune_process(4242, priority="high", affinity=0x0F, kernel32=k)
    check("priority raised", k.priority == B.HIGH_PRIORITY_CLASS and
          r.priority_before == "normal" and r.priority_after == "high")
    check("affinity applied", r.affinity_after == hex(0x0F))
    check("throttling opt-out called", len(k.throttling_calls) == 1)
    check("handles closed", k.closed == 1)

    k2 = FakeKernel32()
    k2.priority = B.HIGH_PRIORITY_CLASS
    r = B.tune_process(1, priority="normal", kernel32=k2)
    check("priority lowered", k2.priority == B.NORMAL_PRIORITY_CLASS)
    check("no affinity change when not requested", r.affinity_after == "?")


def test_report():
    print("== report ==")
    check("checklist mentions MaxRenderScale", "MaxRenderScale" in B.REPORT)
    check("checklist mentions Fast lasers", "Fast lasers" in B.REPORT)
    check("checklist mentions affinity", "affinity" in B.REPORT)


def main():
    test_ini()
    with tempfile.TemporaryDirectory() as tmp:
        test_profiles(tmp)
    test_tune()
    test_report()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
