# -- services/gateway/rate_limit.lua
local redis = require "resty.redis"
local red = redis:new()

red:set_timeout(100) 

local ok, err = red:connect("rag-redis-prod", 6379)

if not ok then return ngx.exit(500) end
local key = "rate_limit:" .. ngx.var.remote_addr

local limit = 100

local current = red:incr(key)

if current == 1 then red:expire(key, 60) end

if current > limit then
    ngx.status = 429
    ngx.say("Rate limit exceeded.")
    return ngx.exit(429)
end