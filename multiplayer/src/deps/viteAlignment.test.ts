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

/**
 * Why multiplayer/package.json declares `vite` although nothing here
 * imports it.
 *
 * vitest runs on vite, and the frontend's vite plugins (hoisted to the repo
 * root by npm workspaces) also resolve vite *from the root*. When nothing
 * pinned the root copy, npm placed a vite 8 there for those plugins while the
 * frontend's own vite 6 sat nested in frontend/node_modules — and vite 8 has
 * no esbuild, so `npm run dev` failed on a clean install with "Cannot find
 * module 'esbuild'". Declaring the same range here means both workspaces ask
 * for it, npm hoists exactly one vite to the root, and every plugin, the
 * frontend and this package's vitest share it.
 *
 * These checks fail loudly if the two ranges drift apart (e.g. a dependabot
 * bump of only the frontend) or the root lockfile ever holds two vites again.
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

const ROOT = join(__dirname, "..", "..", "..")

function readJson(...parts: string[]): Record<string, any> {
  return JSON.parse(readFileSync(join(ROOT, ...parts), "utf8"))
}

describe("vite version alignment", () => {
  it("multiplayer pins the same vite range as the frontend", () => {
    const frontend = readJson("frontend", "package.json").devDependencies.vite
    const multiplayer = readJson("multiplayer", "package.json").devDependencies.vite
    expect(frontend).toBeTruthy()
    expect(multiplayer).toBe(frontend)
  })

  it("the root lockfile resolves exactly one vite", () => {
    const packages: Record<string, { version?: string }> = readJson("package-lock.json").packages
    const versions = new Set(
      Object.entries(packages)
        .filter(([path]) => /(^|\/)node_modules\/vite$/.test(path))
        .map(([, meta]) => meta.version),
    )
    expect([...versions]).toHaveLength(1)
  })
})
