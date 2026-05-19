<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="640"
    persistent
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="dialog-card">
      <!-- Header -->
      <header class="dialog-header">
        <div class="dialog-icon">
          <v-icon icon="mdi-robot-happy-outline" size="20" />
        </div>
        <div class="dialog-title-wrap">
          <h3 class="dialog-title">New custom skill</h3>
          <div class="dialog-sub">
            Plugs in alongside the seeded defaults. Promote to default
            when ready.
          </div>
        </div>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          density="comfortable"
          @click="close"
        />
      </header>

      <v-divider />

      <!-- Body -->
      <div class="dialog-body">
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          {{ errorMessage }}
        </v-alert>

        <!-- Import bar — accepts a .md file with YAML frontmatter and splits
             it across the right fields, so pasting an off-the-shelf skill
             from the Claude Code catalog "just works". -->
        <div class="import-row">
          <div class="import-text">
            <v-icon icon="mdi-import" size="14" class="mr-1" />
            Import an existing skill file
          </div>
          <v-btn
            variant="tonal"
            color="primary"
            size="small"
            class="text-none"
            prepend-icon="mdi-upload-outline"
            @click="triggerImport"
          >
            Choose .md
          </v-btn>
          <input
            ref="fileInputEl"
            type="file"
            accept=".md,text/markdown,text/plain"
            class="hidden-file"
            @change="onFileSelected"
          >
        </div>
        <v-snackbar
          v-model="showImportToast"
          :timeout="3500"
          location="top right"
          color="primary"
          variant="elevated"
        >
          {{ importToast }}
        </v-snackbar>

        <div class="field-grid">
          <div class="field col-6">
            <label class="field-label">Agent type</label>
            <v-select
              v-model="form.agentType"
              :items="agentTypeItems"
              item-title="title"
              item-value="value"
              variant="outlined"
              density="compact"
              hide-details
            />
          </div>

          <div class="field col-6">
            <label class="field-label">Slug</label>
            <v-text-field
              v-model="form.skillSlug"
              placeholder="my-pm"
              variant="outlined"
              density="compact"
              :error-messages="slugError ? [slugError] : []"
              hide-details="auto"
            />
            <div v-if="!slugError" class="field-hint">
              Lowercase, hyphens only — unique within agent type
            </div>
          </div>

          <div class="field col-12">
            <label class="field-label">Display name</label>
            <v-text-field
              v-model="form.name"
              placeholder="e.g. Concise PM"
              variant="outlined"
              density="compact"
              hide-details
            />
          </div>

          <div class="field col-12">
            <label class="field-label">Description</label>
            <v-text-field
              v-model="form.description"
              placeholder="One line shown next to the skill name"
              variant="outlined"
              density="compact"
              hide-details
            />
          </div>

          <div class="field col-12">
            <label class="field-label">Prompt</label>
            <v-textarea
              v-model="form.prompt"
              placeholder="# Skill&#10;&#10;You are…"
              variant="outlined"
              density="compact"
              rows="9"
              auto-grow
              hide-details
              class="prompt-textarea"
              @paste="onPromptPaste"
            />
            <div class="field-hint">
              Tip: paste a full <code>.md</code> file and the YAML frontmatter
              is split into the other fields automatically.
            </div>
          </div>

          <div class="field col-6">
            <label class="field-label">Tools</label>
            <v-combobox
              v-model="form.tools"
              placeholder="Read, Write, Edit…"
              variant="outlined"
              density="compact"
              multiple
              chips
              closable-chips
              hide-details
            />
          </div>

          <div class="field col-6">
            <label class="field-label">MCP tools</label>
            <v-combobox
              v-model="form.mcpTools"
              placeholder="get_bud_context…"
              variant="outlined"
              density="compact"
              multiple
              chips
              closable-chips
              hide-details
            />
          </div>

          <div class="field col-6">
            <label class="field-label">Model</label>
            <v-select
              v-model="form.model"
              :items="modelOptions"
              item-title="title"
              item-value="value"
              variant="outlined"
              density="compact"
              hide-details
            />
          </div>

          <div class="field col-6">
            <label class="field-label">Max turns</label>
            <v-text-field
              v-model.number="form.maxTurns"
              type="number"
              :min="0"
              :max="100"
              variant="outlined"
              density="compact"
              hide-details
            />
            <div class="field-hint">0 = unlimited</div>
          </div>
        </div>
      </div>

      <v-divider />

      <!-- Footer -->
      <footer class="dialog-footer">
        <v-spacer />
        <v-btn variant="text" class="text-none" @click="close">
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          class="text-none"
          :loading="store.saving"
          :disabled="!canSubmit"
          @click="submit"
        >
          Create skill
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AGENT_TYPE_LABELS,
  type AgentType,
  useAgentSkillsStore,
} from '@/stores/agentSkills'

const props = defineProps<{
  modelValue: boolean
  initialAgentType?: AgentType | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const store = useAgentSkillsStore()
const errorMessage = ref<string | null>(null)
const fileInputEl = ref<HTMLInputElement | null>(null)
const showImportToast = ref(false)
const importToast = ref('')

interface FormState {
  agentType: AgentType
  skillSlug: string
  name: string
  description: string
  prompt: string
  tools: string[]
  mcpTools: string[]
  model: string
  maxTurns: number
}

// Pre-fill the form from the seeded skill for ``agentType``. Gives the
// user a working starting point so creating a custom skill is "edit the
// template", not "find every tool name from memory". When no seed has
// been loaded yet (store still fetching), returns a blank form.
function templateForAgent(agentType: AgentType): FormState {
  const seed = store.skills.find(s => s.agentType === agentType && !s.isCustom)
  if (!seed) {
    return {
      agentType,
      skillSlug: '',
      name: '',
      description: '',
      prompt: '',
      tools: [],
      mcpTools: [],
      model: '',
      maxTurns: 0,
    }
  }
  return {
    agentType,
    skillSlug: `${seed.skillSlug}-copy`,
    name: `Copy of ${seed.name}`,
    description: seed.description,
    prompt: seed.prompt,
    tools: [...seed.tools],
    mcpTools: [...seed.mcpTools],
    model: seed.model,
    maxTurns: seed.maxTurns,
  }
}

const form = ref<FormState>(templateForAgent(props.initialAgentType ?? 'bud'))

const agentTypeItems = computed(() =>
  (Object.keys(AGENT_TYPE_LABELS) as AgentType[]).map(value => ({
    value,
    title: AGENT_TYPE_LABELS[value],
  })),
)

const modelOptions = [
  { title: 'Default', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
]

const SLUG_REGEX = /^[a-z0-9][a-z0-9-]*$/

const slugError = computed<string | null>(() => {
  if (form.value.skillSlug === '') return null
  return SLUG_REGEX.test(form.value.skillSlug)
    ? null
    : 'Lowercase letters, digits, and hyphens only'
})

const canSubmit = computed(
  () =>
    form.value.name.trim().length > 0 &&
    form.value.prompt.trim().length > 0 &&
    SLUG_REGEX.test(form.value.skillSlug),
)

watch(
  () => props.modelValue,
  open => {
    if (open) {
      form.value = templateForAgent(props.initialAgentType ?? 'bud')
      errorMessage.value = null
    }
  },
)

// Re-fill the template when the user switches agent type while the
// dialog is open — keeps prompt/tools/etc. in sync with whichever
// agent's defaults they're now starting from.
watch(
  () => form.value.agentType,
  (newAt, oldAt) => {
    if (!props.modelValue) return
    if (newAt === oldAt) return
    form.value = templateForAgent(newAt)
  },
)

function close(): void {
  emit('update:modelValue', false)
}

// ── .md import ──────────────────────────────────────────────────────
//
// Skill files in the wild (Claude Code catalog, anthropics samples, etc.)
// are shaped like:
//
//   ---
//   name: foo
//   description: …
//   tools: Read, Write
//   ---
//
//   # Foo
//   You are …
//
// The "tools" line is sometimes comma-separated, sometimes whitespace.
// We strip the frontmatter, split it into the form's metadata fields,
// and put the body in the Prompt field — same shape we expect from
// users authoring from scratch.

// Parsed frontmatter — only the six fields we consume downstream.
// Optional because any field may be absent from a real file.
interface ParsedMeta {
  name?: string
  description?: string
  tools?: string
  mcp_tools?: string
  model?: string
  max_turns?: string
}

interface ParsedFrontmatter {
  meta: ParsedMeta
  body: string
}

function _stripQuotes(value: string): string {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1)
  }
  return value
}

function parseFrontmatter(text: string): ParsedFrontmatter | null {
  const match = text.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n?([\s\S]*)$/)
  if (!match) return null
  const yamlBlock = match[1]
  const body = match[2] ?? ''
  // Explicit switch on literal keys instead of ``meta[userKey] = value``.
  // The dynamic-property-write form (even guarded by a runtime Set.has)
  // tripped CodeQL's "Remote property injection" rule, since a malicious
  // .md with ``__proto__: …`` or ``constructor: …`` lines would be
  // tainted user input flowing into a property name. With a switch the
  // assignment targets are compile-time literals — there's no dataflow
  // edge for CodeQL to flag, and unknown keys are dropped on the floor.
  const meta: ParsedMeta = {}
  for (const line of yamlBlock.split(/\r?\n/)) {
    const kv = line.match(/^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$/)
    if (!kv) continue
    const key = kv[1]
    const value = _stripQuotes(kv[2].trim())
    switch (key) {
      case 'name':
        meta.name = value
        break
      case 'description':
        meta.description = value
        break
      case 'tools':
        meta.tools = value
        break
      case 'mcp_tools':
        meta.mcp_tools = value
        break
      case 'model':
        meta.model = value
        break
      case 'max_turns':
        meta.max_turns = value
        break
      // any other key (incl. __proto__, constructor) is silently ignored
    }
  }
  return { meta, body: body.replace(/^\r?\n+/, '') }
}

function splitListValue(value: string): string[] {
  return value
    .split(/[,\s]+/)
    .map(s => s.trim())
    .filter(Boolean)
}

function slugifyName(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
}

const MODEL_VALUES = new Set(['', 'sonnet', 'opus', 'haiku'])

function applyImport(text: string, source: 'file' | 'paste'): boolean {
  const parsed = parseFrontmatter(text)
  if (!parsed) return false

  const { meta, body } = parsed
  const touched: string[] = []

  if (meta.name) {
    form.value.name = meta.name
    touched.push('name')
    if (!form.value.skillSlug) {
      form.value.skillSlug = slugifyName(meta.name)
      touched.push('slug')
    }
  }
  if (meta.description) {
    form.value.description = meta.description
    touched.push('description')
  }
  if (meta.tools) {
    form.value.tools = splitListValue(meta.tools)
    touched.push('tools')
  }
  if (meta.mcp_tools) {
    form.value.mcpTools = splitListValue(meta.mcp_tools)
    touched.push('mcp_tools')
  }
  if (meta.model && MODEL_VALUES.has(meta.model)) {
    form.value.model = meta.model
    touched.push('model')
  }
  if (meta.max_turns) {
    const n = Number(meta.max_turns)
    if (Number.isFinite(n)) {
      form.value.maxTurns = n
      touched.push('max_turns')
    }
  }

  form.value.prompt = body
  importToast.value =
    source === 'file'
      ? `Imported ${touched.length} field${touched.length === 1 ? '' : 's'} from file`
      : `Stripped frontmatter and split ${touched.length} field${touched.length === 1 ? '' : 's'}`
  showImportToast.value = true
  return true
}

function triggerImport(): void {
  fileInputEl.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  // Reset the input so re-selecting the same file still fires @change.
  target.value = ''
  if (!file) return
  try {
    const text = await file.text()
    if (!applyImport(text, 'file')) {
      // No frontmatter — treat the whole file as a prompt body.
      form.value.prompt = text.trim()
      importToast.value = 'Loaded prompt body (no frontmatter detected)'
      showImportToast.value = true
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to read file'
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

async function submit(): Promise<void> {
  errorMessage.value = null
  const created = await store.createCustomSkill({
    skillSlug: form.value.skillSlug,
    agentType: form.value.agentType,
    name: form.value.name.trim(),
    description: form.value.description.trim(),
    prompt: form.value.prompt,
    tools: form.value.tools,
    mcpTools: form.value.mcpTools,
    model: form.value.model,
    maxTurns: form.value.maxTurns,
  })
  if (created) {
    emit('created')
    close()
  } else {
    errorMessage.value = store.error ?? 'Failed to create custom skill.'
  }
}
</script>

<style scoped>
.dialog-card {
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  background: rgb(var(--v-theme-surface));
  border-radius: 14px;
  overflow: hidden;
}

/* ── Header ───────────────────────────────────────────────── */

.dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  flex-shrink: 0;
}

.dialog-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.dialog-icon .v-icon { color: rgb(var(--v-theme-primary)); }

.dialog-title-wrap { flex: 1; min-width: 0; }
.dialog-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 2px;
  color: rgb(var(--v-theme-on-surface));
}
.dialog-sub {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  line-height: 1.45;
}

/* ── Body ─────────────────────────────────────────────────── */

.dialog-body {
  padding: 16px 18px;
  overflow-y: auto;
  flex: 1;
}

.import-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 14px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.18);
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.import-text {
  flex: 1;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  display: flex;
  align-items: center;
}

.hidden-file {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.field-hint code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 10.5px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 4px;
  border-radius: 3px;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  column-gap: 12px;
  row-gap: 14px;
}

.col-6 { grid-column: span 6; }
.col-12 { grid-column: 1 / -1; }

@media (max-width: 600px) {
  .col-6 { grid-column: 1 / -1; }
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
  color: rgba(var(--v-theme-on-surface), 0.78);
  line-height: 1;
}

.field-hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  line-height: 1.3;
  margin-top: 1px;
}

.prompt-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.55;
}

.prompt-textarea :deep(.v-field) {
  background: rgba(0, 0, 0, 0.18);
}

/* Shrink Vuetify's default outlined-field min-height to match label-above
   convention. Density 'compact' already lowers it; this nudges harder for
   selects whose item slot bumps the height back up. */
:deep(.v-field--variant-outlined.v-field--density-compact) {
  --v-field-padding-top: 0;
}
:deep(.v-field--variant-outlined .v-field__input) {
  min-height: 38px;
  padding-top: 4px;
  padding-bottom: 4px;
}

/* ── Footer ───────────────────────────────────────────────── */

.dialog-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  flex-shrink: 0;
}
</style>
