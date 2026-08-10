#!/usr/bin/env python3
"""IsaacFPS smoke test.

Runs the mod's Lua against a stubbed Isaac API (via lupa, an embedded Lua
runtime) and asserts that every feature behaves. Dev-only tool; the game
itself never loads anything from tools/.

Usage:  python3 tools/smoketest.py
"""

import os
import sys

try:
    from lupa import LuaRuntime
except ImportError:
    sys.exit("lupa is required: pip install lupa")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SETUP = r"""
FAKE = { time = 0, frame = 0, paused = false, saved = nil }
CONSOLE_LINES = {}
DEBUG_LINES = {}
DRAW_CALLS = 0
SFX_PLAYS = 0

ModCallback = { POST_UPDATE = 1, POST_RENDER = 2, PRE_GAME_EXIT = 78 }

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

Callbacks = {}
function RegisterMod(name, api)
    return {
        name = name,
        AddCallback = function(self, cbid, fn)
            Callbacks[cbid] = Callbacks[cbid] or {}
            table.insert(Callbacks[cbid], fn)
        end,
        SaveModData = function(self, data) FAKE.saved = data end,
        LoadModData = function(self) return FAKE.saved end,
        HasModData = function(self) return FAKE.saved ~= nil end,
    }
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

function FireCallbacks(id)
    for _, fn in ipairs(Callbacks[id] or {}) do fn() end
end
"""

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


def main():
    os.chdir(ROOT)
    lua = LuaRuntime()
    lua.globals()["READ_FILE"] = read_lua_file
    lua.execute(SETUP)

    print("== boot ==")
    lua.execute("assert(loadfile('resources/scripts/main.lua'))()")
    g = lua.globals()
    I = g["IsaacFPS"]
    check("IsaacFPS loaded", I and I["Loaded"] is True)
    check("boot console message",
          any("IsaacFPS" in l and "loaded" in l for l in lua_list(g["CONSOLE_LINES"])))
    check("two frame callbacks registered",
          len(g["Callbacks"][1]) == 1 and len(g["Callbacks"][2]) == 1)
    check("audio patched", I["Audio"]["Patched"] is True)
    check("debug filter patched", I["DebugFilter"]["Patched"] is True)
    check("gc profile applied", I["GC"]["ActiveProfile"] == 1)
    check("gc reachable", isinstance(I["GC"]["MemoryKB"](), float))

    def step(n, ms_per_frame=16, updates=True):
        for _ in range(n):
            g["FAKE"]["frame"] += 1
            g["FAKE"]["time"] += ms_per_frame
            if updates:
                lua.execute("FireCallbacks(1)")
            lua.execute("FireCallbacks(2)")

    print("== overlay ==")
    step(10)
    check("overlay drew", g["DRAW_CALLS"] > 0)
    check("frame time measured", abs(I["State"]["emaMs"] - 16) < 3,
          f"(emaMs={I['State']['emaMs']})")
    step(25)
    check("entity count", I["State"]["entityCount"] == 3)

    print("== config ==")
    lua.execute("fpsset('targetFPS', 144)")
    check("config set", I["Config"]["Values"]["targetFPS"] == 144)
    check("config saved with type tag",
          g["FAKE"]["saved"] and "targetFPS:n:144" in str(g["FAKE"]["saved"]))
    lua.execute(r"""
        local s = IsaacFPS.Config.Serialize()
        IsaacFPS.Config.Values.targetFPS = 60
        IsaacFPS.Config.Deserialize(s)
    """)
    check("serialize/deserialize round trip",
          I["Config"]["Values"]["targetFPS"] == 144)
    lua.execute("fpsset('overlay', false)")
    before = g["DRAW_CALLS"]
    step(3)
    check("overlay off stops drawing", g["DRAW_CALLS"] == before)
    lua.execute("fpsoverlay()")
    step(3)
    check("fpsoverlay toggles back", g["DRAW_CALLS"] > before)
    check("unknown key rejected", lua.eval("IsaacFPS.Config.Set('nope', 1)") is False)

    print("== audio dedupe ==")
    lua.execute("SFX_PLAYS = 0")
    lua.execute("for _ = 1, 5 do SFXManager():Play('SOUND_TEST') end")
    check("same-frame repeats dropped", g["SFX_PLAYS"] == 1,
          f"(plays={g['SFX_PLAYS']})")
    step(1)
    lua.execute("SFXManager():Play('SOUND_TEST')")
    check("within window still dropped", g["SFX_PLAYS"] == 1)
    step(2)
    lua.execute("SFXManager():Play('SOUND_TEST')")
    check("after window plays again", g["SFX_PLAYS"] == 2)
    lua.execute("SFXManager():Play('SOUND_TEST', 1, 0, true)")
    check("looped sounds never dropped", g["SFX_PLAYS"] == 3)
    lua.execute("fpsset('audioDedupe', false)")
    check("unpatch on disable", I["Audio"]["Patched"] is False)
    lua.execute("SFX_PLAYS = 0")
    lua.execute("for _ = 1, 5 do SFXManager():Play('SOUND_TEST') end")
    check("disabled = all plays pass", g["SFX_PLAYS"] == 5)
    lua.execute("fpsset('audioDedupe', true)")
    check("repatch on enable", I["Audio"]["Patched"] is True)

    print("== debug log filter ==")
    before_dbg = len(g["DEBUG_LINES"])
    lua.execute("for _ = 1, 10 do Isaac.DebugString('same message') end")
    check("repeats suppressed", len(g["DEBUG_LINES"]) == before_dbg + 1)
    lua.execute("Isaac.DebugString('different message')")
    check("new message passes + summary", len(g["DEBUG_LINES"]) == before_dbg + 3)
    lua.execute("fpsset('debugFilter', false)")
    before_dbg = len(g["DEBUG_LINES"])
    lua.execute("Isaac.DebugString('x') Isaac.DebugString('x')")
    check("unpatched passes everything", len(g["DEBUG_LINES"]) == before_dbg + 2)
    lua.execute("fpsset('debugFilter', true)")

    print("== throttle library ==")
    # Deterministic: no automatic detail changes during these measurements.
    lua.execute("fpsset('targetFPS', 60) fpsset('autoTune', false)")
    lua.execute(r"""
        TASK_RUNS = 0
        TASK_HANDLE = IsaacFPS.AddRender(function() TASK_RUNS = TASK_RUNS + 1 end, 10)
    """)
    lua.execute("TASK_RUNS = 0")
    step(100)
    check("interval-10 task runs 10x in 100 frames", g["TASK_RUNS"] == 10,
          f"(runs={g['TASK_RUNS']})")
    lua.execute("IsaacFPS.RemoveTask(TASK_HANDLE)")
    lua.execute("TASK_RUNS = 0")
    step(30)
    check("removed task stops running", g["TASK_RUNS"] == 0)
    lua.execute(r"""
        SCALED_RUNS = 0
        IsaacFPS.AddRender(function() SCALED_RUNS = SCALED_RUNS + 1 end, 10)
        IsaacFPS.SetDetail(2)
    """)
    lua.execute("SCALED_RUNS = 0")
    step(100)
    check("detail x2 halves scaled task rate", g["SCALED_RUNS"] == 5,
          f"(runs={g['SCALED_RUNS']})")
    lua.execute("IsaacFPS.SetDetail(1)")

    print("== pause freeze ==")
    lua.execute("PAUSE_RUNS = 0")
    lua.execute("IsaacFPS.AddRender(function() PAUSE_RUNS = PAUSE_RUNS + 1 end, 1)")
    step(5)
    paused_runs = g["PAUSE_RUNS"]
    check("tasks run unpaused", paused_runs == 5)
    g["FAKE"]["paused"] = True
    lua.execute("PAUSE_RUNS = 0")
    step(5)
    check("tasks frozen while paused", g["PAUSE_RUNS"] == 0)
    g["FAKE"]["paused"] = False

    print("== cache library ==")
    lua.execute(r"""
        COMPUTES = 0
        for _ = 1, 20 do
            IsaacFPS.Cache.Get('k', 10, function() COMPUTES = COMPUTES + 1 return 42 end)
        end
    """)
    check("cache recomputes once per ttl", g["COMPUTES"] == 1,
          f"(computes={g['COMPUTES']})")
    check("shared font cache", lua.eval("IsaacFPS.Font() == IsaacFPS.Font()") is True)

    print("== autotune ==")
    lua.execute("fpsset('targetFPS', 60) fpsset('autoTune', true)")
    step(200, ms_per_frame=100)  # ~10 fps, below 90% of target
    check("detail raised under load", I["State"]["detail"] >= 2,
          f"(detail={I['State']['detail']})")
    step(120, ms_per_frame=100)
    check("detail capped at 3", I["State"]["detail"] == 3)
    step(1000, ms_per_frame=8)    # ~125 fps, above 135% of target
    check("detail recovers with headroom", I["State"]["detail"] == 1,
          f"(detail={I['State']['detail']})")

    print("== spikes ==")
    check("spikes recorded from slow frames", I["Spikes"]["Count"]() > 0)
    before_c = len(lua_list(g["CONSOLE_LINES"]))
    lua.execute("fpsreport()")
    check("fpsreport prints", len(lua_list(g["CONSOLE_LINES"])) > before_c)

    print("== console commands ==")
    for cmd in ("fps()", "fpskeys()", "fpshelp()", "fpsmem()", "fpsget('overlay')"):
        before_c = len(lua_list(g["CONSOLE_LINES"]))
        lua.execute(cmd)
        check(f"{cmd} prints", len(lua_list(g["CONSOLE_LINES"])) > before_c)

    print("== benchmark ==")
    lua.execute("fpsbench(1)")
    step(70, ms_per_frame=16)  # 70 frames * 16 ms > 1 s
    bench_done = any("avg" in l and "fps" in l for l in lua_list(g["CONSOLE_LINES"]))
    check("fpsbench completes", bench_done)

    print("== persistence + guards ==")
    lua.execute("FireCallbacks(78)")  # PRE_GAME_EXIT
    check("config saved on exit", g["FAKE"]["saved"] is not None)
    before_dbg = len(lua_list(g["DEBUG_LINES"]))
    lua.execute("assert(loadfile('resources/scripts/main.lua'))()")
    check("duplicate load skipped",
          any("already loaded" in l for l in lua_list(g["DEBUG_LINES"])[before_dbg:]))

    print()
    print(f"{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
