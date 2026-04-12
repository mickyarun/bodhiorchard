/**
 * Shared helpers for rendering developer activity rows.
 *
 * Used by both BUDDevelopmentPanel.vue and BUDQATestingActivity.vue.
 * Extracted from BUDDevelopmentPanel.vue so the testing tab doesn't have
 * to duplicate the file-icon / time-format logic — keeping them in sync
 * by hand was already creating drift risk before the testing tab existed.
 */

/**
 * Render a relative-time string for an ISO date (e.g. "5m ago", "2h ago").
 *
 * Uses the same thresholds the dev panel had inlined: minute / hour / day,
 * then falls back to a fixed "Nd ago" label. Not localised — the dev tab
 * never localised it either, and consistency between tabs matters more
 * than i18n correctness for an internal devtool surface.
 */
export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

/**
 * Parse the comma-separated `files_changed` string from a commit row
 * into a clean list, dropping empty entries.
 */
export function parseFiles(raw: string): string[] {
  if (!raw) return []
  return raw.split(',').map(f => f.trim()).filter(Boolean)
}

/**
 * Pick a Material Design icon name for a file path based on its extension.
 *
 * Recognises Vue / TS / JS / Python / CSS / Markdown / JSON+YAML+TOML and
 * test files (anything with "test" or "spec" in the path). Unknown
 * extensions get a generic file outline.
 */
export function fileIcon(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (['vue', 'tsx', 'jsx'].includes(ext)) return 'mdi-vuejs'
  if (['ts', 'js'].includes(ext)) return 'mdi-language-typescript'
  if (['py'].includes(ext)) return 'mdi-language-python'
  if (['css', 'scss'].includes(ext)) return 'mdi-palette'
  if (['md'].includes(ext)) return 'mdi-file-document'
  if (['json', 'yaml', 'yml', 'toml'].includes(ext)) return 'mdi-code-json'
  if (['test', 'spec'].some(t => path.includes(t))) return 'mdi-test-tube'
  return 'mdi-file-outline'
}

/**
 * Pick a Material Design palette color for a file path based on its
 * extension. Used to colour-code file rows in the contributor activity
 * lists. Test files get purple to make them visually distinct from
 * production code, which matches the QA-tab branding too.
 */
export function fileColor(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (['vue', 'tsx', 'jsx'].includes(ext)) return 'teal'
  if (['ts', 'js'].includes(ext)) return 'blue'
  if (['py'].includes(ext)) return 'amber'
  if (['test', 'spec'].some(t => path.includes(t))) return 'purple'
  return 'grey'
}
