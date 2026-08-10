#!/usr/bin/env python3
"""IsaacFPS smoke test.

Runs the mod's Lua against a stubbed Isaac API (via lupa, an embedded Lua
runtime) and asserts that every feature behaves. Two scenarios:

  * vanilla     - plain Repentance API (no REPENTOGON)
  * repentogon  - with REPENTOGON stubs (native sfx hook, console API,
                  ImGui, nano timing, MC_POST_MODS_LOADED)

Dev-only tool; the game itself never loads anything from tools/.

Usage:  python3 tools/smoketest.py
"""

import os
import sys

try:
    from lupa import LuaRuntime
except ImportError:
    sys.exit("lupa is required: pip install lupa")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def lua_list(table):
    """Materialize a Lua array (1-based) into a Python list of strings."""
    if table is None:
        return []
    out = []
    i = 1
    while table[i] is not None:
        out.append(str(table[i]))
        i += 1
    return out


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f" FAIL {name} {extra}")


def read_lua_file(path):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    with open(full, "r", encoding="utf-8") as fh:
        return fh.read()


BASE_SETUP = r"""
FAKE = { time = 0, frame = 0, paused = false, saved = nil }
CONSOLE_LINES = {}
DEBUG_LINES = {}
DRAW_CALLS = 0
SFX_PLAYS = 0

function Color(r, g, b, a, ro, go, bo)
    return { r = r, g = g, b = b, a = a }
end

Isaac = {}
function Isaac.GetTime() return FAKE.time end
function Isaac.GetFrameCount() return FAKE.frame end
function Isaac.Console(s) CONSOLE_LINES[#CONSOLE_LINES + 1] = tostring(s) end
function Isaac.DebugString(s) DEBUG_LINES[#DEBUG_LINES + 1] = tostring(s) end
function Isaac.GetScreenSize() return { X = 480, Y = 270 } end
function Isaac.GetRoomEntities() return { { id = 1 }, { id = 2 }, { id = 3 } } end

function Font(path)
    return {
        path = path,
        DrawString = function(self, ...) DRAW_CALLS = DRAW_CALLS + 1 end,
        GetStringWidth = function(self, s) return #s * 5 end,
        IsLoaded = function(self) return true end,
    }
end

GameInstance = {
    IsPaused = function(self) return FAKE.paused end,
    GetLevel = function(self)
        return { GetStage = function(self) return "STAGE_TEST" end }
    end,
}
function Game() return GameInstance end

local sfxClass = {}
function sfxClass.Play(self, sound, volume, frameDelay, loop, pitch, pan)
    SFX_PLAYS = SFX_PLAYS + 1
end
local sfxInstance = setmetatable({}, { __index = sfxClass })
function SFXManager() return sfxInstance end

CallbackRecords = {}
function RegisterMod(name, api)
    return {
        name = name,
        AddCallback = function(self, cbid, fn, opt)
            CallbackRecords[cbid] = CallbackRecords[cbid] or {}
            table.insert(CallbackRecords[cbid], { fn = fn, opt = opt })
        end,
        SaveModData = function(self, data) FAKE.saved = data end,
        LoadModData = function(self) return FAKE.saved end,
        HasModData = function(self) return FAKE.saved ~= nil end,
    }
end

function FireCallbacks(id)
    for _, rec in ipairs(CallbackRecords[id] or {}) do rec.fn() end
end

function FindCallback(id, opt)
    for _, rec in ipairs(CallbackRecords[id] or {}) do
        if opt == nil or rec.opt == opt then return rec.fn end
    end
    return nil
end

function loadfile(path)
    local src = READ_FILE(path)
    if src == nil then return nil, "cannot open " .. tostring(path) end
    return load(src, "@" .. path)
end

function include(path)
    local fn, err = loadfile("resources/scripts/" .. path)
    if not fn then error("include failed for " .. path .. ": " .. tostring(err)) end
    return fn()
end
"""

VANILLA_SETUP = BASE_SETUP + r"""
-- Old-style enum table only: exercises the ModCallbacks/ModCallback fallback.
ModCallback = { POST_UPDATE = 1, POST_RENDER = 2, PRE_GAME_EXIT = 78 }
"""

REPENTOGON_SETUP = BASE_SETUP + r"""
ModCallbacks = {
    MC_POST_UPDATE = 1,
    MC_POST_RENDER = 2,
    MC_PRE_GAME_EXIT = 78,
    MC_PRE_SFX_PLAY = 1030,
    MC_POST_SFX_PLAY = 1031,
    MC_CONSOLE_AUTOCOMPLETE = 1120,
    MC_POST_MODS_LOADED = 1210,
}

REPENTOGON = {
    Version = "1.0.12a",
    MeetsVersion = function(v) return true end,
}

function Isaac.GetNanoTime() return FAKE.time * 1000000 + 123456 end

RGCONSOLE = { commands = {}, macros = {} }
Console = {
    RegisterCommand = function(name, desc, helptext, showOnMenu, acType)
        RGCONSOLE.commands[name] = { desc = desc, helptext = helptext,
                                     showOnMenu = showOnMenu, acType = acType }
    end,
    RegisterMacro = function(name, commands)
        RGCONSOLE.macros[name] = commands
    end,
    GetHistory = function() return {} end,
}

AutocompleteType = { NONE = 0, CUSTOM = 18 }
ImGuiElement = { Window = 0, Menu = 1, MenuItem = 2, Separator = 6, SameLine = 11 }
ImGuiData = { Label = 0, Value = 1, ListValues = 2, HintText = 5 }
ImGuiCallback = { Render = 10 }
ImGuiNotificationType = { INFO = 0, WARNING = 1, ERROR = 2 }

ImGuiCalls = {}
local function imguiCapture(kind)
    return function(...)
        ImGuiCalls[#ImGuiCalls + 1] = { kind = kind, args = { ... } }
    end
end
ImGui = {
    CreateMenu = imguiCapture("CreateMenu"),
    CreateWindow = imguiCapture("CreateWindow"),
    LinkWindowToElement = imguiCapture("LinkWindowToElement"),
    AddElement = imguiCapture("AddElement"),
    AddText = imguiCapture("AddText"),
    AddPlotLines = imguiCapture("AddPlotLines"),
    AddPlotHistogram = imguiCapture("AddPlotHistogram"),
    AddCheckbox = imguiCapture("AddCheckbox"),
    AddSliderInteger = imguiCapture("AddSliderInteger"),
    AddCombobox = imguiCapture("AddCombobox"),
    AddButton = imguiCapture("AddButton"),
    SetHelpmarker = imguiCapture("SetHelpmarker"),
    SetVisible = imguiCapture("SetVisible"),
    GetVisible = function(id) return true end,
    UpdateData = imguiCapture("UpdateData"),
    UpdateText = imguiCapture("UpdateText"),
    PushNotification = imguiCapture("PushNotification"),
}

function CountImGuiCalls(kind, arg1)
    local n = 0
    for _, c in ipairs(ImGuiCalls) do
        if c.kind == kind and (arg1 == nil or c.args[1] == arg1) then
            n = n + 1
        end
    end
    return n
end
"""


class Scenario:
    def __init__(self, setup):
        self.lua = LuaRuntime()
        self.lua.globals()["READ_FILE"] = read_lua_file
        self.lua.execute(setup)

    def g(self):
        return self.lua.globals()

    def exec(self, code):
        self.lua.execute(code)

    def boot(self):
        self.exec("assert(loadfile('resources/scripts/main.lua'))()")
        return self.g()["IsaacFPS"]

    def step(self, n, ms_per_frame=16):
        g = self.g()
        for _ in range(n):
            g["FAKE"]["frame"] += 1
            g["FAKE"]["time"] += ms_per_frame
            self.exec("FireCallbacks(1)")  # POST_UPDATE
            self.exec("FireCallbacks(2)")  # POST_RENDER


def run_vanilla():
    print("=============== scenario: vanilla Repentance ===============")
    s = Scenario(VANILLA_SETUP)
    g = s.g()
    I = s.boot()

    print("== boot ==")
    check("IsaacFPS loaded", I and I["Loaded"] is True)
    check("boot console message",
          any("IsaacFPS" in l and "loaded" in l for l in lua_list(g["CONSOLE_LINES"])))
    check("two frame callbacks registered",
          len(g["CallbackRecords"][1]) == 1 and len(g["CallbackRecords"][2]) == 1)
    check("audio patched (wrapper mode)", I["Audio"]["Patched"] is True)
    check("audio native off", I["Audio"]["Native"] is False)
    check("debug filter patched", I["DebugFilter"]["Patched"] is True)
    check("gc profile applied", I["GC"]["ActiveProfile"] == 1)
    check("gc reachable", isinstance(I["GC"]["MemoryKB"](), float))
    check("REPENTOGON not detected", I["RG"]["Active"] in (False, None))

    print("== overlay ==")
    s.step(10)
    check("overlay drew", g["DRAW_CALLS"] > 0)
    check("frame time measured", abs(I["State"]["emaMs"] - 16) < 3,
          f"(emaMs={I['State']['emaMs']})")
    s.step(25)
    check("entity count", I["State"]["entityCount"] == 3)

    print("== config ==")
    s.exec("fpsset('targetFPS', 144)")
    check("config set", I["Config"]["Values"]["targetFPS"] == 144)
    check("config saved with type tag",
          g["FAKE"]["saved"] and "targetFPS:n:144" in str(g["FAKE"]["saved"]))
    s.exec(r"""
        local ser = IsaacFPS.Config.Serialize()
        IsaacFPS.Config.Values.targetFPS = 60
        IsaacFPS.Config.Deserialize(ser)
    """)
    check("serialize/deserialize round trip",
          I["Config"]["Values"]["targetFPS"] == 144)
    s.exec("fpsset('overlay', false)")
    before = g["DRAW_CALLS"]
    s.step(3)
    check("overlay off stops drawing", g["DRAW_CALLS"] == before)
    s.exec("fpsoverlay()")
    s.step(3)
    check("fpsoverlay toggles back", g["DRAW_CALLS"] > before)
    check("unknown key rejected", s.lua.eval("IsaacFPS.Config.Set('nope', 1)") is False)

    print("== audio dedupe (wrapper) ==")
    s.exec("SFX_PLAYS = 0")
    s.exec("for _ = 1, 5 do SFXManager():Play('SOUND_TEST') end")
    check("same-frame repeats dropped", g["SFX_PLAYS"] == 1,
          f"(plays={g['SFX_PLAYS']})")
    s.step(1)
    s.exec("SFXManager():Play('SOUND_TEST')")
    check("within window still dropped", g["SFX_PLAYS"] == 1)
    s.step(2)
    s.exec("SFXManager():Play('SOUND_TEST')")
    check("after window plays again", g["SFX_PLAYS"] == 2)
    s.exec("SFXManager():Play('SOUND_TEST', 1, 0, true)")
    check("looped sounds never dropped", g["SFX_PLAYS"] == 3)
    s.exec("fpsset('audioDedupe', false)")
    check("unpatch on disable", I["Audio"]["Patched"] is False)
    s.exec("SFX_PLAYS = 0")
    s.exec("for _ = 1, 5 do SFXManager():Play('SOUND_TEST') end")
    check("disabled = all plays pass", g["SFX_PLAYS"] == 5)
    s.exec("fpsset('audioDedupe', true)")
    check("repatch on enable", I["Audio"]["Patched"] is True)

    print("== debug log filter ==")
    before_dbg = len(g["DEBUG_LINES"])
    s.exec("for _ = 1, 10 do Isaac.DebugString('same message') end")
    check("repeats suppressed", len(g["DEBUG_LINES"]) == before_dbg + 1)
    s.exec("Isaac.DebugString('different message')")
    check("new message passes + summary", len(g["DEBUG_LINES"]) == before_dbg + 3)
    s.exec("fpsset('debugFilter', false)")
    before_dbg = len(g["DEBUG_LINES"])
    s.exec("Isaac.DebugString('x') Isaac.DebugString('x')")
    check("unpatched passes everything", len(g["DEBUG_LINES"]) == before_dbg + 2)
    s.exec("fpsset('debugFilter', true)")

    print("== throttle library ==")
    s.exec("fpsset('targetFPS', 60) fpsset('autoTune', false)")
    s.exec(r"""
        TASK_RUNS = 0
        TASK_HANDLE = IsaacFPS.AddRender(function() TASK_RUNS = TASK_RUNS + 1 end, 10)
    """)
    s.exec("TASK_RUNS = 0")
    s.step(100)
    check("interval-10 task runs 10x in 100 frames", g["TASK_RUNS"] == 10,
          f"(runs={g['TASK_RUNS']})")
    s.exec("IsaacFPS.RemoveTask(TASK_HANDLE)")
    s.exec("TASK_RUNS = 0")
    s.step(30)
    check("removed task stops running", g["TASK_RUNS"] == 0)
    s.exec(r"""
        SCALED_RUNS = 0
        IsaacFPS.AddRender(function() SCALED_RUNS = SCALED_RUNS + 1 end, 10)
        IsaacFPS.SetDetail(2)
    """)
    s.exec("SCALED_RUNS = 0")
    s.step(100)
    check("detail x2 halves scaled task rate", g["SCALED_RUNS"] == 5,
          f"(runs={g['SCALED_RUNS']})")
    s.exec("IsaacFPS.SetDetail(1)")

    print("== pause freeze ==")
    s.exec("PAUSE_RUNS = 0")
    s.exec("IsaacFPS.AddRender(function() PAUSE_RUNS = PAUSE_RUNS + 1 end, 1)")
    s.step(5)
    check("tasks run unpaused", g["PAUSE_RUNS"] == 5)
    g["FAKE"]["paused"] = True
    s.exec("PAUSE_RUNS = 0")
    s.step(5)
    check("tasks frozen while paused", g["PAUSE_RUNS"] == 0)
    g["FAKE"]["paused"] = False

    print("== cache library ==")
    s.exec(r"""
        COMPUTES = 0
        for _ = 1, 20 do
            IsaacFPS.Cache.Get('k', 10, function() COMPUTES = COMPUTES + 1 return 42 end)
        end
    """)
    check("cache recomputes once per ttl", g["COMPUTES"] == 1,
          f"(computes={g['COMPUTES']})")
    check("shared font cache", s.lua.eval("IsaacFPS.Font() == IsaacFPS.Font()") is True)

    print("== autotune ==")
    s.exec("fpsset('targetFPS', 60) fpsset('autoTune', true)")
    s.step(200, ms_per_frame=100)  # ~10 fps, below 90% of target
    check("detail raised under load", I["State"]["detail"] >= 2,
          f"(detail={I['State']['detail']})")
    s.step(120, ms_per_frame=100)
    check("detail capped at 3", I["State"]["detail"] == 3)
    s.step(1000, ms_per_frame=8)    # ~125 fps, above 135% of target
    check("detail recovers with headroom", I["State"]["detail"] == 1,
          f"(detail={I['State']['detail']})")

    print("== spikes ==")
    check("spikes recorded from slow frames", I["Spikes"]["Count"]() > 0)
    before_c = len(lua_list(g["CONSOLE_LINES"]))
    s.exec("fpsreport()")
    check("fpsreport prints", len(lua_list(g["CONSOLE_LINES"])) > before_c)

    print("== console commands ==")
    for cmd in ("fps()", "fpskeys()", "fpshelp()", "fpsmem()", "fpsget('overlay')"):
        before_c = len(lua_list(g["CONSOLE_LINES"]))
        s.exec(cmd)
        check(f"{cmd} prints", len(lua_list(g["CONSOLE_LINES"])) > before_c)

    print("== benchmark ==")
    s.exec("fpsbench(1)")
    s.step(70, ms_per_frame=16)  # 70 frames * 16 ms > 1 s
    bench_done = any("avg" in l and "fps" in l for l in lua_list(g["CONSOLE_LINES"]))
    check("fpsbench completes", bench_done)

    print("== persistence + guards ==")
    s.exec("FireCallbacks(78)")  # PRE_GAME_EXIT
    check("config saved on exit", g["FAKE"]["saved"] is not None)
    before_dbg = len(lua_list(g["DEBUG_LINES"]))
    s.exec("assert(loadfile('resources/scripts/main.lua'))()")
    check("duplicate load skipped",
          any("already loaded" in l for l in lua_list(g["DEBUG_LINES"])[before_dbg:]))


def run_repentogon():
    print()
    print("=============== scenario: with REPENTOGON ===============")
    s = Scenario(REPENTOGON_SETUP)
    g = s.g()
    I = s.boot()

    print("== detection ==")
    check("REPENTOGON detected", I["RG"]["Active"] is True)
    check("version captured", I["RG"]["Version"] == "1.0.12a")
    check("native sfx hook available", I["RG"]["HasPreSfxCallback"] is True)
    check("console API available", I["RG"]["HasConsoleAPI"] is True)
    check("ImGui available", I["RG"]["HasImGui"] is True)
    check("nano timing available", I["RG"]["HasNanoTime"] is True)
    check("boot message mentions REPENTOGON",
          any("REPENTOGON" in l for l in lua_list(g["CONSOLE_LINES"])))

    print("== native audio dedupe ==")
    check("native mode active", I["Audio"]["Native"] is True)
    check("wrapper NOT active", I["Audio"]["Patched"] is False)
    sfx_cb = s.lua.eval("FindCallback(1030)")
    check("MC_PRE_SFX_PLAY callback registered", sfx_cb is not None)
    s.exec("NATIVE_RET = {}")
    s.exec("for i = 1, 5 do NATIVE_RET[i] = FindCallback(1030)(42, 1, 0, false, 1, 0) end")
    rets = [s.lua.eval(f"NATIVE_RET[{i}]") for i in range(1, 6)]
    check("first play passes, repeats cancelled",
          rets[0] is None and all(r is False for r in rets[1:]),
          f"(rets={rets})")
    check("looped sound passes", s.lua.eval("FindCallback(1030)(42, 1, 0, true, 1, 0)") is None)
    check("different sound passes", s.lua.eval("FindCallback(1030)(99, 1, 0, false, 1, 0)") is None)
    s.exec("fpsset('audioDedupe', false)")
    check("disabled = duplicate passes",
          s.lua.eval("FindCallback(1030)(42, 1, 0, false, 1, 0)") is None)
    s.exec("fpsset('audioDedupe', true)")
    check("re-enabled = duplicate cancelled",
          s.lua.eval("FindCallback(1030)(42, 1, 0, false, 1, 0)") is False)
    s.exec("SFX_PLAYS = 0")
    s.exec("for _ = 1, 3 do SFXManager():Play('X') end")
    check("SFXManager not patched in native mode", g["SFX_PLAYS"] == 3)

    print("== console integration ==")
    cmds = g["RGCONSOLE"]["commands"]
    for name in ("fps", "fpshelp", "fpskeys", "fpsget", "fpsset",
                 "fpsoverlay", "fpsbench", "fpsreport", "fpsmem"):
        check(f"command registered: {name}", cmds[name] is not None)
    check("fpsset uses CUSTOM autocomplete", cmds["fpsset"]["acType"] == 18)
    check("fps uses NONE autocomplete", cmds["fps"]["acType"] == 0)
    check("macro fps -> fps()",
          lua_list(g["RGCONSOLE"]["macros"]["fps"]) == ["fps()"])
    check("macro fpsreport -> fpsreport()",
          lua_list(g["RGCONSOLE"]["macros"]["fpsreport"]) == ["fpsreport()"])
    ac = s.lua.eval("FindCallback(1120, 'fpsset')")
    check("autocomplete callback registered for fpsset", ac is not None)
    s.exec("AC_RESULT = FindCallback(1120, 'fpsset')('fpsset', '')")
    opts = s.lua.eval("""
        (function()
            local found = false
            for _, entry in ipairs(AC_RESULT) do
                if entry[1] == 'overlay' and entry[2] ~= '' then found = true end
            end
            return found
        end)()
    """)
    check("autocomplete offers config keys with descriptions", opts is True)

    print("== ImGui dashboard ==")
    check("menu created", s.lua.eval("CountImGuiCalls('CreateMenu', 'isaacfps_menu')") == 1)
    check("performance window created",
          s.lua.eval("CountImGuiCalls('CreateWindow', 'isaacfps_perf')") == 1)
    check("settings window created",
          s.lua.eval("CountImGuiCalls('CreateWindow', 'isaacfps_settings')") == 1)
    check("checkboxes added", s.lua.eval("CountImGuiCalls('AddCheckbox')") >= 5)
    check("sliders added", s.lua.eval("CountImGuiCalls('AddSliderInteger')") >= 3)
    check("gc combobox added", s.lua.eval("CountImGuiCalls('AddCombobox')") == 1)
    check("bench buttons added", s.lua.eval("CountImGuiCalls('AddButton')") >= 2)
    s.step(40)
    check("plots updated",
          s.lua.eval("CountImGuiCalls('UpdateData', 'isaacfps_framePlot')") >= 1)
    check("status text updated",
          s.lua.eval("CountImGuiCalls('UpdateText', 'isaacfps_perfStatus')") >= 1)

    print("== GC awareness ==")
    check("gc profile 1 keeps REPENTOGON generational default",
          I["GC"]["ActiveProfile"] == 1)
    check("log explains the deferral",
          any("generational GC default" in l for l in lua_list(g["DEBUG_LINES"])))

    print("== nanosecond timing ==")
    s.step(6)
    ema = I["State"]["emaMs"]
    check("ema reflects nano clock (fractional ms)",
          abs(ema - 16.123456) < 0.5, f"(emaMs={ema})")

    print("== notifications + late init ==")
    s.exec("fpsset('targetFPS', 60)")
    s.step(200, ms_per_frame=100)  # force autotune to raise detail
    check("detail raised under load (RG scenario)", I["State"]["detail"] >= 2)
    check("ImGui notification pushed on autotune",
          s.lua.eval("CountImGuiCalls('PushNotification')") >= 1)
    before_c = len(lua_list(g["CONSOLE_LINES"]))
    s.exec("FireCallbacks(1210)")  # MC_POST_MODS_LOADED
    check("post-mods-loaded summary prints",
          any("all mods loaded" in l for l in lua_list(g["CONSOLE_LINES"])[before_c:]))

    print("== fallback safety ==")
    s.exec("FireCallbacks(78)")  # MC_PRE_GAME_EXIT
    check("config saved on exit", g["FAKE"]["saved"] is not None)


def main():
    os.chdir(ROOT)
    run_vanilla()
    run_repentogon()
    print()
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
