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
 * .md import for the "New custom skill" dialog: a chosen file or a pasted
 * skill with YAML frontmatter is split across the form's fields, and a
 * toast says how many were filled.
 */
import { ref, type Ref } from 'vue'
import type { CustomSkillForm } from '@/components/settings/customSkill/customSkillForm.util'
import {
  applyParsedImport,
  importToastMessage,
  parseFrontmatter,
  type ImportSource,
} from '@/components/settings/customSkill/customSkillImport.util'

export function useCustomSkillImport(form: Ref<CustomSkillForm>) {
  const showImportToast = ref(false)
  const importToast = ref('')

  function showToast(message: string): void {
    importToast.value = message
    showImportToast.value = true
  }

  function applyImport(text: string, source: ImportSource): boolean {
    const parsed = parseFrontmatter(text)
    if (!parsed) return false
    const touched = applyParsedImport(form.value, parsed)
    showToast(importToastMessage(source, touched.length))
    return true
  }

  function onFileLoaded(text: string): void {
    if (!applyImport(text, 'file')) {
      // No frontmatter — treat the whole file as a prompt body.
      form.value.prompt = text.trim()
      showToast('Loaded prompt body (no frontmatter detected)')
    }
  }

  function onPromptPaste(event: ClipboardEvent): void {
    const pasted = event.clipboardData?.getData('text/plain')
    if (!pasted || !pasted.startsWith('---')) return
    // Only intercept if it actually parses — otherwise let the default
    // paste behaviour drop the text in unchanged.
    if (applyImport(pasted, 'paste')) {
      event.preventDefault()
    }
  }

  return { showImportToast, importToast, onFileLoaded, onPromptPaste }
}
