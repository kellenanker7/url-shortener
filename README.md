# URL Shortener

```bash
npm install
sls create-cert
poetry export --without-hashes --f requirements.txt -o requirements.txt --with-credentials
sls deploy --stage live
```

## Metrics
```bash
# Service status
curl 'https://kell.link/api/status'
{"status":"alive"}

# Get all clicks, grouped by suid and long_url
curl 'https://kell.link/api/clicks' -H "x-kellink-token: let-me-in"
{"clicks_by_suid":{"rLFlJY":"606"},"click_by_long_url":{"https://www.youtube.com/watch?v=dQw4w9WgXcQ":"644"}}

# Get all clicks, for specific suid
curl 'https://kell.link/api/clicks?suid=rLFlJY' -H "x-kellink-token: let-me-in"
{"rLFlJY":"606"}

# Get all clicks, for specific long_url
curl 'https://kell.link/api/clicks?long_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ' -H "x-kellink-token: let-me-in"
{"https://www.youtube.com/watch?v=dQw4w9WgXcQ":"644"}
```
