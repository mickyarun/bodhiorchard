# Dev merge backup

Local-only helper for iterating on the cross-repo feature merge phase.
Snapshots the three tables Phase B3 mutates so you can rewind a botched
merge run without re-scanning every repo.

## Tables captured

- `synthesized_features` — immutable per-scan audit (B3 stamps `merge_outcome`, `merged_into_id`, `superseded_at`)
- `knowledge_items` — feature registry (B3 flips `is_active=false` on absorbed rows, may insert new canonicals)
- `knowledge_to_repo` — junction (B3 transfers links from absorbed → canonical)

## Usage

```bash
# 1. Snapshot before testing
./backend/scripts/dev_merge_backup/dump.sh
# → writes backups/merge_YYYYMMDD_HHMMSS.sql

# 2. Run a scan / trigger merge however you like

# 3. If the result is bad, restore + iterate
./backend/scripts/dev_merge_backup/restore.sh \
  backend/scripts/dev_merge_backup/backups/merge_YYYYMMDD_HHMMSS.sql
```

## Connection

Defaults to the local docker compose dev DB (`test:test@localhost:5432/bodhiorchard`).
Override via env if your setup differs:

```bash
PGHOST=... PGPORT=... PGUSER=... PGPASSWORD=... PGDATABASE=... ./dump.sh
```

## Safety

`restore.sh` refuses if `PGDATABASE` contains `prod`, `production`, or `live`.
Set `FORCE_RESTORE=1` to override only if you're certain.

## Not for production

This is dev tooling. Production merge issues should use the existing
`POST /scan/reset` endpoint, which is the supported nuclear-reset path.
