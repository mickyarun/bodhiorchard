# glideship

One command to run the [Glideship](https://github.com/mickyarun/glideship) stack locally. Pulls
prebuilt Docker images and starts everything — Postgres (pgvector), Redis, the
API, the realtime server, and the web UI — then opens the setup wizard.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) (Desktop or Engine) running
- Node.js 22+

## Quick start

```bash
npx glideship init     # scaffold ./glideship, resolve ports, pull images
cd glideship
npx glideship start     # bring it up and open http://localhost:3000/setup
```

Finish configuration (organization, admin account, AI provider, repositories) in
the browser setup wizard. No keys or secrets are entered on the command line.

## Ports already in use?

If something is already listening on Postgres (5432), Redis (6379), or an app
port (8000 / 3000 / 2567), `init` detects it and asks whether to:

- **Use a different host port** — keep the bundled service, bind it elsewhere; or
- **Reuse the existing service** — point the app at what's already running.

Redis reuse is offered freely. Postgres reuse is opt-in via
`--allow-postgres-reuse` and is verified to have the `pgvector` extension before
it's accepted (Glideship requires it).

Run fully non-interactively with `--yes` (auto-remaps any conflict).

## Commands

| Command | Description |
| --- | --- |
| `init [name]` | Scaffold an install directory and pull images |
| `start` | Start the stack and open the setup wizard |
| `stop` | Stop the stack (data is preserved) |
| `status` | Show container status and access URLs |
| `logs [service]` | Follow container logs |
| `update [--tag X.Y.Z]` | Pull newer images and restart |
| `reset [--yes]` | Stop and delete all data volumes (destructive) |

Use `--project-dir <path>` to target an install that isn't in the current
directory.

## Upgrading from `bodhiorchard`

This package used to be published as `bodhiorchard`. Existing installs keep
working: run the new CLI from inside your install directory and it switches the
install over to the renamed images, keeping your data.

```bash
cd bodhiorchard          # your existing install directory
npx glideship update
```

The install directory, its `.bodhiorchard/` config folder and the data volumes
keep their names, so nothing needs to be moved or migrated.
