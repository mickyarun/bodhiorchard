#!/usr/bin/env bash
# Bring up the dev stack — backend + frontend + multiplayer + infra.
#
# Detects whether Postgres (5432) and Redis (6379) are already reachable
# on localhost. If both are up, prompts whether to skip the
# ``docker compose up`` step — the previous flow would crash here with
# "port already allocated" if the user had infra running from another
# session (e.g. an orphaned dev stack, or a stack started in a different
# checkout / worktree). Skipping lets the app processes attach to the
# existing infra cleanly.
#
# Behaviour summary:
#   * Both ports bound + TTY        → prompt, default Y (skip).
#   * Both ports bound + no TTY     → auto-skip (CI / IDE task runner).
#   * Either port free              → run full ``docker compose up`` flow.
#   * ``FORCE_INFRA=1`` env override → always run the full flow.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

POSTGRES_PORT=5432
REDIS_PORT=6379

is_port_open() {
  # ``nc -z`` returns 0 if the TCP probe succeeds. ``-G 1`` caps the
  # connect timeout on macOS so a firewalled port doesn't hang the
  # script; -w on Linux. Try macOS flag first, fall back.
  nc -z -G 1 localhost "$1" >/dev/null 2>&1 || nc -z -w 1 localhost "$1" >/dev/null 2>&1
}

run_apps() {
  exec npx --no-install concurrently \
    -n backend,frontend,multiplayer \
    -c blue,green,magenta \
    "npm:dev:backend" "npm:dev:frontend" "npm:dev:multiplayer"
}

run_full_stack() {
  npm run dev:infra
  npm run dev:infra:wait
  run_apps
}

# Explicit override — useful when you've intentionally torn infra down
# and want the script to recreate it without prompting.
if [[ "${FORCE_INFRA:-0}" == "1" ]]; then
  echo "[dev-start] FORCE_INFRA=1 — running full infra startup."
  run_full_stack
fi

if is_port_open "$POSTGRES_PORT" && is_port_open "$REDIS_PORT"; then
  echo "[dev-start] Postgres (:${POSTGRES_PORT}) and Redis (:${REDIS_PORT}) are already up."

  # Default to skip. If stdin is a TTY, give the user a chance to override.
  skip="y"
  if [[ -t 0 ]]; then
    read -r -p "[dev-start] Skip infra startup? [Y/n] " answer || true
    case "${answer:-Y}" in
      n|N|no|NO) skip="n" ;;
      *)         skip="y" ;;
    esac
  else
    echo "[dev-start] Non-interactive shell — auto-skipping infra."
  fi

  if [[ "$skip" == "y" ]]; then
    echo "[dev-start] Skipping docker compose; starting app processes only."
    run_apps
  fi
fi

echo "[dev-start] Bringing up infra + app processes."
run_full_stack
