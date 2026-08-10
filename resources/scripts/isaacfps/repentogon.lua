-- IsaacFPS :: REPENTOGON integration (fully optional).
-- REPENTOGON (https://repentogon.com) is a script extender that hooks the
-- game's C++ internals. When it is installed, IsaacFPS upgrades itself:
--
--   * Sound dedupe runs through the native MC_PRE_SFX_PLAY hook instead of
--     a metatable patch.
--   * Console commands are registered properly (autocomplete, help, macros).
--   * An ImGui performance dashboard (frame time + memory graphs, live
--     settings, benchmark buttons) is added to the REPENTOGON menu.
--   * Frame timing uses Isaac.GetNanoTime() for sub-millisecond precision.
--   * GC tuning steps aside: REPENTOGON already enables Lua 5.4's
--     generational collector by default, which is the best setting.
--
-- Nothing here is required: without REPENTOGON every feature either falls
-- back to its vanilla implementation or stays disabled.

local I = IsaacFPS
if not I then return end
local U = I.Util

local RG = {}
I.RG = RG

local PFX = "isaacfps_" -- element id prefix, REPENTOGON ids are global

-- ---------------------------------------------------------------------------
-- Detection (runs at include time, before IsaacFPS applies its settings).
-- ---------------------------------------------------------------------------
function RG.Detect()
    RG.Active = (type(REPENTOGON) == "table")
    RG.Version = RG.Active and tostring(REPENTOGON.Version or "?") or nil
    local MC = ModCallbacks
    RG.HasPreSfxCallback = RG.Active and MC ~= nil and MC.MC_PRE_SFX_PLAY ~= nil
    RG.HasPostModsLoaded = RG.Active and MC ~= nil and MC.MC_POST_MODS_LOADED ~= nil
    RG.HasConsoleAPI = RG.Active and type(Console) == "table"
        and type(Console.RegisterCommand) == "function"
    RG.HasImGui = RG.Active and type(ImGui) == "table"
        and type(ImGui.CreateMenu) == "function"
    RG.HasNanoTime = RG.Active and type(Isaac.GetNanoTime) == "function"
    if RG.Active then
        U.Log("REPENTOGON detected (version " .. tostring(RG.Version)
            .. ") - native sfx hook: " .. tostring(RG.HasPreSfxCallback ~= nil)
            .. ", console API: " .. tostring(RG.HasConsoleAPI)
            .. ", ImGui: " .. tostring(RG.HasImGui)
            .. ", nano timing: " .. tostring(RG.HasNanoTime))
    end
end

RG.Detect()

-- ---------------------------------------------------------------------------
-- Console integration: registered commands, macros and autocomplete.
-- ---------------------------------------------------------------------------
local COMMANDS = {
    -- name, description, help text, custom autocomplete?
    { "fps",        "IsaacFPS status (fps, memory, detail)", "Prints the IsaacFPS status overview." },
    { "fpshelp",    "list all IsaacFPS commands",            "Lists every IsaacFPS console command." },
    { "fpskeys",    "list all IsaacFPS settings",            "Lists every IsaacFPS setting with its current value." },
    { "fpsget",     "read an IsaacFPS setting",              "Usage: fpsget('key'). Tab completes keys.", true },
    { "fpsset",     "change an IsaacFPS setting",            "Usage: fpsset('key', value). Saved automatically. Tab completes keys.", true },
    { "fpsoverlay", "toggle the IsaacFPS overlay",           "Toggles the FPS/stats overlay." },
    { "fpsbench",   "benchmark: fpsbench(seconds)",          "Samples frames for N seconds and reports avg / 1% low / worst frame." },
    { "fpsreport",  "show recorded frame spikes",            "Shows stage, entity count and Lua memory for every recorded hitch." },
    { "fpsmem",     "Lua memory report + GC sweep",          "Shows the Lua heap size and how much a full GC sweep reclaims." },
}

local MACROS = {
    { "fps",        { "fps()" } },
    { "fpshelp",    { "fpshelp()" } },
    { "fpskeys",    { "fpskeys()" } },
    { "fpsoverlay", { "fpsoverlay()" } },
    { "fpsreport",  { "fpsreport()" } },
    { "fpsmem",     { "fpsmem()" } },
}

local function sortedConfigKeys()
    local keys = {}
    for k in pairs(I.Config.Defaults) do keys[#keys + 1] = k end
    table.sort(keys)
    return keys
end

function RG.InitConsole()
    if not RG.HasConsoleAPI then return end
    U.Try("console registration", function()
        local MC = ModCallbacks
        local AT = AutocompleteType or {}
        local NONE = AT.NONE or 0
        local CUSTOM = AT.CUSTOM or 18

        for _, c in ipairs(COMMANDS) do
            Console.RegisterCommand(c[1], c[2], c[3], true, c[4] and CUSTOM or NONE)
        end
        for _, m in ipairs(MACROS) do
            Console.RegisterMacro(m[1], m[2])
        end

        if MC and MC.MC_CONSOLE_AUTOCOMPLETE then
            local function configAutocomplete(command, params)
                local out = {}
                for _, k in ipairs(sortedConfigKeys()) do
                    out[#out + 1] = { k, I.Config.Help[k] or "" }
                end
                return out
            end
            I.Mod:AddCallback(MC.MC_CONSOLE_AUTOCOMPLETE, configAutocomplete, "fpsset")
            I.Mod:AddCallback(MC.MC_CONSOLE_AUTOCOMPLETE, configAutocomplete, "fpsget")
        end
        U.Log("Console commands registered (" .. #COMMANDS
            .. " commands, " .. #MACROS .. " macros).")
    end)
end

-- ---------------------------------------------------------------------------
-- ImGui dashboard: frame time + memory graphs, live stats, settings.
-- ---------------------------------------------------------------------------
local frameHistory = {} -- last N frame times in ms
local memHistory = {}   -- last N Lua heap samples in MB
local HISTORY_CAP = 120

local function pushSample(t, v)
    t[#t + 1] = v
    while #t > HISTORY_CAP do
        table.remove(t, 1)
    end
end

local uiBuilt = false

function RG.InitImGui()
    if not RG.HasImGui or uiBuilt then return end
    local ok, err = pcall(function()
        local IE = ImGuiElement or {}
        local cfg = I.Config

        -- Menu entry in the REPENTOGON top bar (opens with the console key).
        ImGui.CreateMenu(PFX .. "menu", "\u{f0e4} IsaacFPS")
        ImGui.AddElement(PFX .. "menu", PFX .. "perfButton", IE.MenuItem or 2,
            "\u{f201} Performance")
        ImGui.AddElement(PFX .. "menu", PFX .. "settingsButton", IE.MenuItem or 2,
            "\u{f013} Settings")

        -- Performance window -------------------------------------------------
        ImGui.CreateWindow(PFX .. "perf", "IsaacFPS - Performance")
        ImGui.LinkWindowToElement(PFX .. "perf", PFX .. "perfButton")
        ImGui.AddText(PFX .. "perf",
            "IsaacFPS v" .. I.Version .. "  |  REPENTOGON " .. tostring(RG.Version),
            true, PFX .. "perfHeader")
        ImGui.AddPlotLines(PFX .. "perf", PFX .. "framePlot",
            "Frame time (ms, last " .. HISTORY_CAP .. " frames)", {}, "", 0, 33.3, 80)
        ImGui.AddPlotHistogram(PFX .. "perf", PFX .. "memPlot",
            "Lua memory (MB)", {}, "", 0, 0, 60)
        ImGui.AddText(PFX .. "perf", "", false, PFX .. "perfStatus")
        ImGui.AddText(PFX .. "perf", "", false, PFX .. "perfSpikes")
        ImGui.AddElement(PFX .. "perf", "", IE.Separator or 6)
        ImGui.AddButton(PFX .. "perf", PFX .. "bench5", "Benchmark 5s",
            function() I.Bench.Run(5) end)
        ImGui.AddElement(PFX .. "perf", "", IE.SameLine or 11)
        ImGui.AddButton(PFX .. "perf", PFX .. "bench15", "Benchmark 15s",
            function() I.Bench.Run(15) end)
        ImGui.AddElement(PFX .. "perf", "", IE.SameLine or 11)
        ImGui.AddButton(PFX .. "perf", PFX .. "spikeClearNote", "Spike report: fpsreport()", nil, true)

        -- Settings window -----------------------------------------------------
        ImGui.CreateWindow(PFX .. "settings", "IsaacFPS - Settings")
        ImGui.LinkWindowToElement(PFX .. "settings", PFX .. "settingsButton")
        ImGui.AddText(PFX .. "settings",
            "Changes apply live and are saved automatically.", true)

        ImGui.AddCheckbox(PFX .. "settings", PFX .. "cbOverlay", "FPS overlay",
            function(v) I.Config.Set("overlay", v) end, cfg.Get("overlay"))
        ImGui.AddCheckbox(PFX .. "settings", PFX .. "cbAudio", "Sound spam dedupe",
            function(v) I.Config.Set("audioDedupe", v) end, cfg.Get("audioDedupe"))
        ImGui.AddCheckbox(PFX .. "settings", PFX .. "cbLog", "Debug log spam filter",
            function(v) I.Config.Set("debugFilter", v) end, cfg.Get("debugFilter"))
        ImGui.AddCheckbox(PFX .. "settings", PFX .. "cbPause", "Freeze mod rendering while paused",
            function(v) I.Config.Set("freezeWhenPaused", v) end, cfg.Get("freezeWhenPaused"))
        ImGui.AddCheckbox(PFX .. "settings", PFX .. "cbTune", "Automatic detail scaling",
            function(v) I.Config.Set("autoTune", v) end, cfg.Get("autoTune"))

        ImGui.AddSliderInteger(PFX .. "settings", PFX .. "slTarget", "Target FPS",
            function(v) I.Config.Set("targetFPS", v) end,
            cfg.Get("targetFPS"), 30, 240, "Target FPS: %d")
        ImGui.AddSliderInteger(PFX .. "settings", PFX .. "slWindow", "Sound dedupe window (frames)",
            function(v) I.Config.Set("dedupeWindow", v) end,
            cfg.Get("dedupeWindow"), 1, 10, "Window: %d")
        ImGui.AddSliderInteger(PFX .. "settings", PFX .. "slSpike", "Spike threshold (ms)",
            function(v) I.Config.Set("spikeMs", v) end,
            cfg.Get("spikeMs"), 33, 250, "Threshold: %d")

        local gcIndex = math.floor(tonumber(cfg.Get("gcProfile")) or 1)
        ImGui.AddCombobox(PFX .. "settings", PFX .. "comboGc", "GC profile",
            function(index)
                local v = U.Clamp((tonumber(index) or 1) - 1, 0, 2)
                I.Config.Set("gcProfile", v)
            end,
            { "0 - stock (untouched)", "1 - smooth", "2 - aggressive" },
            gcIndex + 1)
        if RG.Active then
            ImGui.SetHelpmarker(PFX .. "comboGc",
                "Note: REPENTOGON already enables Lua 5.4's generational GC, which profile 1 respects automatically.")
        end
        ImGui.SetHelpmarker(PFX .. "cbTune",
            "When FPS drops below the target, registered mod overlays refresh less often until headroom returns.")

        uiBuilt = true
        U.Log("ImGui dashboard created (menu 'IsaacFPS').")
    end)
    if not ok then
        RG.HasImGui = false
        U.Log("ImGui integration failed: " .. tostring(err))
    end
end

function RG.UpdateUI()
    if not (RG.HasImGui and uiBuilt) then return end

    pushSample(frameHistory, I.State.emaMs or 0)
    local mem = I.GC.MemoryKB()
    if mem then pushSample(memHistory, mem / 1024) end

    U.Try("imgui update", function()
        local ID = ImGuiData or {}
        local listValues = ID.ListValues or 2

        if ImGui.GetVisible(PFX .. "perf") then
            ImGui.UpdateData(PFX .. "framePlot", listValues, frameHistory)
            if #memHistory > 0 then
                ImGui.UpdateData(PFX .. "memPlot", listValues, memHistory)
            end
            local s = I.State
            local fps = (s.emaMs and s.emaMs > 0) and (1000 / s.emaMs) or 0
            ImGui.UpdateText(PFX .. "perfStatus", string.format(
                "FPS %.1f  (%.2f ms)   |   detail x%d   |   entities %s   |   dedupe: %s",
                fps, s.emaMs or 0, s.detail,
                tostring(s.entityCount or "?"),
                I.Audio.Native and "native hook" or (I.Audio.Patched and "wrapper" or "off")))
            local n = I.Spikes.Count()
            ImGui.UpdateText(PFX .. "perfSpikes", n > 0
                and (n .. " frame spike(s) recorded - details: fpsreport()")
                or "No frame spikes recorded this session.")
        end
    end)
end

-- Throttled dashboard refresh (unscaled: diagnostics always run).
I.AddRender(RG.UpdateUI, 15, false)

-- ---------------------------------------------------------------------------
-- Late init: summarize once every mod is loaded.
-- ---------------------------------------------------------------------------
if RG.HasPostModsLoaded then
    U.Try("post mods loaded hook", function()
        I.Mod:AddCallback(ModCallbacks.MC_POST_MODS_LOADED, function()
            Isaac.Console(string.format(
                "[IsaacFPS] all mods loaded | REPENTOGON %s | sfx dedupe: %s | ImGui menu: %s",
                tostring(RG.Version),
                I.Audio.Native and "native" or (I.Audio.Patched and "wrapper" or "off"),
                tostring(uiBuilt)))
        end)
    end)
end

return RG
