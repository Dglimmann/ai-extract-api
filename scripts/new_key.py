import secrets

# generates a strong API key
# example output: ak_live_km2... (url-safe)
prefix = "ak_live_"
key = prefix + secrets.token_urlsafe(32)
print(key)