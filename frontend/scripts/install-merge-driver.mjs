// Best-effort install of npm-merge-driver so package-lock.json merge
// conflicts auto-resolve. Skipped outside a git checkout and never fails
// the install (mirrors the old `... || true`). Cross-platform: the old
// inline `test -d ../.git && ... || true` prepare script was Unix-shell
// only and broke `npm install` on Windows cmd.exe, where `test` is not a
// command (exit code 1 aborts the whole install).
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

// npm runs lifecycle scripts with cwd = the package dir (frontend/), so
// the repo root .git lives one level up.
if (existsSync(join(process.cwd(), '..', '.git'))) {
  const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx'
  spawnSync(
    npx,
    ['--yes', 'npm-merge-driver', 'install', '--driver-name=npm-merge-driver'],
    { stdio: 'inherit' },
  )
}

// Always succeed — installing the merge driver is a convenience, never a
// hard dependency of the build.
process.exit(0)
