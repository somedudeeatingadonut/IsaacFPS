-- IsaacFPS :: sound spam dedupe.
-- In big mod collections it is very common that several mods play the same
-- short sound effect every frame (menu blips, tick sounds, "charge" sounds),
-- which wastes CPU in the audio mixer and can crackle on weaker machines.
--
-- We wrap SFXManager():Play and drop a play when the exact same sound (same
-- id and pitch) was already started within `dedupeWindow` frames, or when
-- too many new sounds start in a single frame. Looped sounds and sounds with
-- a frame delay are never touched.

local I = IsaacFPS
if not I then return end
local U = I.Util

local Audio = {}
I.Audio = Audio

Audio.Patched = false
Audio.OrigPlay = nil

local lastPlayed = {}      -- "sound@pitch" -> frame of last accepted play
local playsThisFrame = 0
local curFrame = -1
local insertions = 0

local function wrappedPlay(self, sound, volume, frameDelay, loop, pitch, pan)
    if not I.Config.Get("audioDedupe") then
        return Audio.OrigPlay(self, sound, volume, frameDelay, loop, pitch, pan)
    end

    local f = Isaac.GetFrameCount()
    if f ~= curFrame then
        curFrame = f
        playsThisFrame = 0
    end

    local fd = frameDelay or 0
    if not loop and fd == 0 then
        local window = (I.Config.Get("dedupeWindow") or 2) + (I.State.detail - 1)
        local key = tostring(sound) .. "@" .. tostring(pitch or 1)
        local last = lastPlayed[key]
        if last and (f - last) < window then
            return -- identical sound is already playing; drop the duplicate
        end
        if playsThisFrame >= (I.Config.Get("maxSoundsPerFrame") or 16) then
            return -- per-frame cap reached
        end
        lastPlayed[key] = f
        insertions = insertions + 1
        if insertions > 4096 then
            lastPlayed = {}
            insertions = 0
        end
    end

    playsThisFrame = playsThisFrame + 1
    return Audio.OrigPlay(self, sound, volume, frameDelay, loop, pitch, pan)
end

function Audio.Patch()
    if Audio.Patched then return true end
    local ok, err = pcall(function()
        local sfx = SFXManager()
        local mt = getmetatable(sfx)
        local cls = mt and mt.__index
        if type(cls) ~= "table" or type(cls.Play) ~= "function" then
            error("SFXManager class table is not patchable")
        end
        Audio.OrigPlay = cls.Play
        cls.Play = wrappedPlay
        Audio.Patched = true
    end)
    if not ok then
        U.Log("Sound dedupe unavailable: " .. tostring(err))
        return false
    end
    U.Log("Sound dedupe active (window=" .. tostring(I.Config.Get("dedupeWindow")) .. " frames).")
    return true
end

function Audio.Unpatch()
    if not Audio.Patched then return end
    pcall(function()
        local cls = getmetatable(SFXManager()).__index
        if Audio.OrigPlay then cls.Play = Audio.OrigPlay end
    end)
    Audio.Patched = false
    Audio.OrigPlay = nil
    U.Log("Sound dedupe disabled (original SFXManager:Play restored).")
end

return Audio
