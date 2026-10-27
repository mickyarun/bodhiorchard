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
 * Shell snippets that set the workspace MCP token as an environment
 * variable. ``BODHIORCHARD_MCP_TOKEN`` is the variable name the generated
 * ``.mcp.json`` reads, so it must not change.
 */

export const MCP_TOKEN_ENV = 'BODHIORCHARD_MCP_TOKEN'
export const MCP_TOKEN_PLACEHOLDER = '<your-bodhiorchard-token>'

export interface ShellSnippet {
  id: 'mac' | 'linux' | 'windows'
  label: string
  icon: string
  code: string
}

export function exportLine(token: string): string {
  return `export ${MCP_TOKEN_ENV}="${token || MCP_TOKEN_PLACEHOLDER}"`
}

export function shellSnippets(token: string): ShellSnippet[] {
  const value = token || MCP_TOKEN_PLACEHOLDER
  return [
    {
      id: 'mac',
      label: 'macOS',
      icon: 'mdi-apple',
      code: `# Add to ~/.zshrc (default shell on macOS)\necho '${exportLine(value)}' >> ~/.zshrc\nsource ~/.zshrc`,
    },
    {
      id: 'linux',
      label: 'Linux',
      icon: 'mdi-linux',
      code: `# Add to ~/.bashrc (or ~/.zshrc if using zsh)\necho '${exportLine(value)}' >> ~/.bashrc\nsource ~/.bashrc`,
    },
    {
      id: 'windows',
      label: 'Windows',
      icon: 'mdi-microsoft-windows',
      code:
        `# PowerShell, set permanently for the current user\n`
        + `[Environment]::SetEnvironmentVariable("${MCP_TOKEN_ENV}", "${value}", "User")\n\n`
        + `# Or from CMD\nsetx ${MCP_TOKEN_ENV} "${value}"`,
    },
  ]
}
