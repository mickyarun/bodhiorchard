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

import { describe, expect, it } from 'vitest'
import { MCP_TOKEN_PLACEHOLDER, exportLine, shellSnippets } from './mcpEnvSnippets'

describe('exportLine', () => {
  it('uses the token, or a placeholder before one exists', () => {
    expect(exportLine('abc')).toBe('export GLIDESHIP_MCP_TOKEN="abc"')
    expect(exportLine('')).toBe(`export GLIDESHIP_MCP_TOKEN="${MCP_TOKEN_PLACEHOLDER}"`)
  })
})

describe('shellSnippets', () => {
  it('writes the variable for each shell', () => {
    const [mac, linux, windows] = shellSnippets('tok')
    expect(mac.code).toContain(`echo 'export GLIDESHIP_MCP_TOKEN="tok"' >> ~/.zshrc`)
    expect(linux.code).toContain('>> ~/.bashrc')
    expect(windows.code).toContain('setx GLIDESHIP_MCP_TOKEN "tok"')
    expect(windows.code).toContain('SetEnvironmentVariable("GLIDESHIP_MCP_TOKEN", "tok", "User")')
  })
})
