-- IsaacFPS :: memoization and shared-object caches.
-- Two of the most common per-frame wastes in mod collections are:
--   1. recomputing values that only change every few frames,
--   2. constructing Font()/Sprite objects every frame instead of reusing them.
-- This module offers both as a tiny opt-in API for any mod:
--
--   local fps = IsaacFPS.Cache.Get("myKey", 6, function()
--       return expensiveComputation()
--   end)                                    -- recomputed every 6 frames max
--
--   local font = IsaacFPS.Font()            -- shared "luamini outlined" font
--   local font = IsaacFPS.Font("font/pftempestasevencomplete.ttf")

local I = IsaacFPS
if not I then return end
local U = I.Util

local Cache = {}
I.Cache = Cache

local store = {}

-- Returns the cached results of fn(); fn runs at most once per `ttl` frames.
function Cache.Get(key, ttl, fn)
    ttl = math.max(1, math.floor(tonumber(ttl) or 1))
    local f = Isaac.GetFrameCount()
    local e = store[key]
    if e and (f - e.frame) < ttl then
        return U.Unpack(e.values, 1, e.values.n)
    end
    local values = U.Pack(fn())
    store[key] = { frame = f, values = values }
    return U.Unpack(values, 1, values.n)
end

function Cache.Invalidate(key)
    if key == nil then
        store = {}
    else
        store[key] = nil
    end
end

-- Shared Font instances, one per font path. --------------------------------
local fonts = {}
function I.Font(path)
    path = path or "font/luamini outlined.otf"
    local f = fonts[path]
    if not f then
        f = Font(path)
        fonts[path] = f
    end
    return f
end

return Cache
