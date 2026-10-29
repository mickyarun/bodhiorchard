// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/** Small local git repositories for specs that add a repo by path. */
import { execFileSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { STACK_HOME } from '../stack/config.ts'

// The developer's own git config (signing, hooks, templates) stays out.
const GIT_ENV = { ...process.env, GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_NOSYSTEM: '1' }

function git(cwd: string, ...args: string[]): void {
  execFileSync('git', ['-c', 'user.name=E2E', '-c', 'user.email=e2e@e2e.example.com', ...args], {
    cwd,
    env: GIT_ENV,
    stdio: 'ignore',
  })
}

/**
 * A repo with `main` and `develop` branches under the backend's home (the
 * only place the repo picker accepts), named `<name>-<random>`.
 */
export function makeGitRepo(name: string): string {
  const dir = path.join(STACK_HOME, 'repos', `${name}-${randomBytes(3).toString('hex')}`)
  mkdirSync(dir, { recursive: true })
  git(dir, 'init', '-q', '-b', 'main')
  writeFileSync(path.join(dir, 'README.md'), `# ${name}\n`)
  writeFileSync(path.join(dir, 'app.py'), 'def health() -> str:\n    return "ok"\n')
  git(dir, 'add', '.')
  git(dir, 'commit', '-q', '-m', 'first commit')
  git(dir, 'branch', 'develop')
  return dir
}
