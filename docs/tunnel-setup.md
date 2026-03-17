# Exposing FlowDev Publicly with Cloudflare Tunnel

FlowDev works fully on localhost without any tunnel. This guide is **optional** — only needed if you want:

- **Slack integration** (webhooks require a public HTTPS URL)
- **Remote access** for org members outside your local network

## Why Cloudflare Tunnel?

| Feature | Cloudflare Tunnel |
|---|---|
| Free? | Yes, no bandwidth limits |
| Custom domain? | Yes, any domain you own |
| Auto HTTPS? | Yes, valid certs, zero config |
| Needs a VPS? | No |
| Production stable? | Yes, widely used |
| Open source client? | Yes (Apache 2.0) |

## Prerequisites

- A domain you own (e.g. `flowdev.yourdomain.com`)
- A free [Cloudflare account](https://dash.cloudflare.com/sign-up) with the domain added to Cloudflare DNS

## Setup Steps

### 1. Install cloudflared

```bash
brew install cloudflare/cloudflare/cloudflared
```

### 2. Authenticate

```bash
cloudflared tunnel login
```

This opens a browser to authorize your Cloudflare account.

### 3. Create a tunnel

```bash
cloudflared tunnel create flowdev
```

Note the tunnel ID printed (e.g. `a1b2c3d4-...`).

### 4. Add DNS routes

```bash
cloudflared tunnel route dns flowdev app.flowdev.yourdomain.com
cloudflared tunnel route dns flowdev api.flowdev.yourdomain.com
```

### 5. Create tunnel config

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: ~/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: app.flowdev.yourdomain.com
    service: http://localhost:3000
  - hostname: api.flowdev.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

Replace `<tunnel-id>` with the ID from step 3.

### 6. Configure environment variables

In `backend/.env`:

```
PUBLIC_URL=https://api.flowdev.yourdomain.com
```

In `frontend/.env` (rebuild the frontend after changing):

```
VITE_API_BASE_URL=https://api.flowdev.yourdomain.com/api
```

### 7. Run the tunnel

**Option A — Directly:**

```bash
cloudflared tunnel run flowdev
```

**Option B — Via Docker Compose:**

Set the tunnel token in `backend/.env`:

```
CLOUDFLARE_TUNNEL_TOKEN=<your-token>
```

Then start with the tunnel profile:

```bash
docker compose --profile tunnel up
```

### 8. Configure Slack webhooks

Set your Slack app's webhook URL to:

```
https://api.flowdev.yourdomain.com/api/v1/slack/events
```

## Optional: Cloudflare Access

[Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/) is free for up to 50 users. It lets you add Google/GitHub SSO to restrict UI access — no code changes needed. Configure it in the Cloudflare Zero Trust dashboard.

## Without a Tunnel (Localhost Only)

FlowDev works fully on:

- **API:** `http://localhost:8000`
- **UI:** `http://localhost:3000`

No tunnel is needed for local development or single-machine use. Note that Slack webhooks won't work without a public URL.
