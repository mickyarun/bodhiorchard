# Backend Docker — Egress Firewall

This directory ships `init-firewall.sh`, the kernel-level egress allow-list
that pairs with the `claude_guard` app-layer defenses. Applies to the
**Full Docker** deployment path only (not Hybrid mode, where the backend
runs on the host venv).

## Why

Every `claude` subprocess we spawn runs under `--dangerously-skip-permissions`.
The app-layer defenses (env scrub, deny list, PreToolUse hook, workspace
pin, JSONL audit) catch known-bad tool calls before they execute, but a
sufficiently novel prompt-injection or a sandbox bypass in the CLI itself
could still phone home. The firewall is the **last line**: even if every
other layer fails, the outbound TCP packet never leaves the container
because the kernel drops it.

## What the firewall allows

By default, only these hosts:

| Host | Why |
|---|---|
| `api.anthropic.com`, `statsig.anthropic.com` | Anthropic API + telemetry |
| `registry.npmjs.org` | Claude Code self-update, MCP server installs |
| `pypi.org`, `files.pythonhosted.org` | pip resolves transitive deps |
| `github.com`, `api.github.com`, `objects.githubusercontent.com`, `codeload.github.com` | Repo clones, PR + check writes |
| `slack.com`, `api.slack.com`, `hooks.slack.com`, `files.slack.com`, `slack-files.com` | Slack bug intake, slack-triage agent, agent-activity fan-out |
| `api.atlassian.com`, `auth.atlassian.com` | Jira OAuth + global API |

Everything else gets `DROP` at the netfilter `OUTPUT` chain.

DNS (UDP+TCP 53) and loopback always pass. Established / related return
traffic for our outbound connections passes.

## Enabling it

The firewall is **opt-in**. Three steps:

### 1. Uncomment the hardening block in `docker-compose.yml`

```yaml
  backend:
    # ...
    cap_drop:
      - ALL
    cap_add:
      - NET_ADMIN        # required so init-firewall.sh can iptables
      - CHOWN            # uvicorn / pip / alembic write logs
      - DAC_OVERRIDE
      - FOWNER
      - SETUID
      - SETGID
      - KILL             # graceful shutdown
    tmpfs:
      - /tmp:rw,size=128M,mode=1777   # MCP tokens land here; wiped on stop
    environment:
      BODHIORCHARD_EGRESS_FIREWALL: "1"
```

### 2. Set `BODHIORCHARD_EGRESS_FIREWALL=1` in the environment

The `entrypoint.sh` checks this flag and runs `init-firewall.sh` BEFORE
alembic and uvicorn. If unset, the script is skipped entirely.

### 3. (If needed) extend the allow-list for customer Jira tenants

Jira Cloud tenants live on `<customer>.atlassian.net` subdomains.
`iptables` resolves hostnames once at boot and can't wildcard, so each
customer subdomain has to be listed explicitly.

Pass a comma-separated list via the compose env:

```yaml
    environment:
      BODHIORCHARD_EGRESS_FIREWALL: "1"
      BODHIORCHARD_EXTRA_ALLOWED_DOMAINS: "acme.atlassian.net,foo.atlassian.net,bar.atlassian.net"
```

The init script will resolve and `ACCEPT` each one alongside the defaults.
The DNS resolution is re-run on every container start, so subdomain IP
churn from Atlassian's CDN is handled automatically.

## When to enable it

| Deployment | Recommendation |
|---|---|
| **Production Linux** (k8s, ECS, bare Docker) | **Enable.** This is the threat model the firewall is designed for. |
| **Mac-mini / Docker Desktop for Mac** | **Skip.** Docker Desktop does not surface `NET_ADMIN` reliably across versions; the firewall init silently no-ops and logs a warning. Hybrid mode + the macOS `sandbox-exec` wrapper (`BODHIORCHARD_HYBRID_SANDBOX=1`) is the better defense on Mac hosts. |
| **CI / ephemeral build runners** | Optional. The agent doesn't run long enough to be worth the lockdown overhead, but enabling it does not hurt. |
| **Local dev (Hybrid `npm run dev`)** | Not applicable — the backend runs on the host, not in a container. Use `BODHIORCHARD_HYBRID_SANDBOX=1` if you want a similar guarantee on macOS. |

## Verifying it works

After `docker compose up`, exec into the backend and try outbound to a
non-allowed host:

```bash
$ docker compose exec backend curl -m 5 https://example.com
curl: (28) Connection timed out after 5000 ms

$ docker compose exec backend curl -sS -o /dev/null -w "%{http_code}\n" https://api.anthropic.com
401
```

If the first command succeeds (or any non-allowed host responds), the
firewall is NOT applied. Check:

1. `BODHIORCHARD_EGRESS_FIREWALL=1` is set in the container env.
2. `NET_ADMIN` is in the `cap_add` list.
3. `entrypoint.sh` log at boot includes
   `==> Applying egress firewall` and
   `init-firewall: egress lockdown applied`.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `init-firewall: iptables not available; skipping` | iptables binary missing from the runtime image | Add `iptables` to the Dockerfile `apt-get install` block (most slim Python images don't include it) |
| `init-firewall: no NET_ADMIN cap; skipping` | Compose missing `cap_add: NET_ADMIN` | Add the cap; re-deploy |
| Claude API works, GitHub clone fails | DNS resolved a new IP after boot that isn't in the rules | Either restart the container, or move that domain to `BODHIORCHARD_EXTRA_ALLOWED_DOMAINS` for explicit re-resolution |
| Jira bug-import fails for a specific customer | Their subdomain isn't in the allow list | Add `<customer>.atlassian.net` to `BODHIORCHARD_EXTRA_ALLOWED_DOMAINS` |
| All outbound fails | The script's "default DROP" applied but the ACCEPT rules failed to land | `docker compose exec backend iptables -L OUTPUT -v -n` to inspect the chain; check the entrypoint log for resolution failures |

## What the firewall does NOT defend against

- **Outbound on already-allowed hosts** — if an attacker can exfiltrate via
  `gist.github.com` or a public Anthropic-hosted endpoint, the firewall
  doesn't help. That's why the app-layer defenses (env scrub, deny list,
  PreToolUse hook) sit in front.
- **TLS-blind exfiltration via DNS** (the egress proxy doesn't intercept
  TLS) — the regex deny list catches `dig`/`nslookup`/`ping` primitives at
  the tool gate before they ever reach the kernel.
- **Lateral movement within the Docker network** — `iptables -P INPUT DROP`
  applies, but service-to-service traffic via container networking still
  flows. That's by design (backend must reach postgres + redis + multiplayer).

The firewall is the **last** Swiss-cheese layer, not a complete defense.
The app-layer deny list, PreToolUse hook, env whitelist, workspace pin,
and JSONL audit cover the rest of the holes.
