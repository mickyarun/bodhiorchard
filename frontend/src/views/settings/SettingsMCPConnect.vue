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

<!-- BYO-AI MCP connect panel. Users can mint scoped named tokens here
     and copy the mcp.json snippet for their local AI client (Claude
     Desktop, Cursor, Continue) so it can read BUD context, search the
     org's knowledge, and consult design systems while drafting PRD /
     design / tech-spec content. -->
<template>
  <v-container fluid class="mcp-page pa-6 pa-md-8">
    <header class="mcp-hero mb-8">
      <div class="d-flex align-center ga-3 mb-2">
        <v-avatar color="primary" size="44" rounded>
          <v-icon icon="mdi-connection" size="24" color="white" />
        </v-avatar>
        <div>
          <h1 class="text-h5 font-weight-bold mb-0">Connect your local AI</h1>
          <div class="text-caption text-medium-emphasis text-uppercase font-weight-medium mcp-hero__eyebrow">
            MCP · Model Context Protocol
          </div>
        </div>
      </div>
      <p class="text-body-2 text-medium-emphasis mcp-hero__lede mt-3">
        Your local AI assistant — Claude Desktop, Cursor, Continue — connects to
        Bodhiorchard via MCP. It can read org context, draft BUDs in chat, and
        save them back through the BYO-AI write surface. Writes are scoped to
        BUDs you are the assignee of, only the field the current phase owns is
        editable, and every change is captured in the History tab for one-click
        revert.
      </p>
    </header>

    <v-card variant="outlined" class="mcp-card mb-6">
      <div class="mcp-card__header">
        <v-icon icon="mdi-link-variant" size="18" color="primary" />
        <div class="text-subtitle-2 font-weight-medium">Endpoint</div>
      </div>
      <div class="mcp-card__body">
        <div class="d-flex align-center ga-2 flex-wrap">
          <code class="endpoint-code flex-grow-1">{{ endpointUrl }}</code>
          <v-btn
            size="small"
            variant="tonal"
            prepend-icon="mdi-content-copy"
            @click="copy(endpointUrl, 'Endpoint copied')"
          >
            Copy
          </v-btn>
        </div>
        <div class="text-caption text-medium-emphasis mt-3">
          Send <code class="inline-code">Authorization: Bearer &lt;token&gt;</code> on
          every request. Stream uses MCP
          <code class="inline-code">2025-03-26/streamable-http</code>.
        </div>
      </div>
    </v-card>

    <v-card variant="outlined" class="mcp-card mb-6">
      <div class="mcp-card__header">
        <v-icon icon="mdi-key-variant" size="18" color="primary" />
        <div class="text-subtitle-2 font-weight-medium">Your tokens</div>
        <v-spacer />
        <v-btn
          color="primary"
          variant="flat"
          size="small"
          prepend-icon="mdi-plus"
          @click="showCreate = true"
        >
          New token
        </v-btn>
      </div>
      <v-divider />
      <div v-if="!tokens.length && !loading" class="empty-state">
        <v-icon icon="mdi-key-plus" size="32" class="text-medium-emphasis" />
        <div class="text-body-2 text-medium-emphasis">
          No tokens yet — create one to connect your local AI.
        </div>
      </div>
      <v-list v-else lines="two" density="comfortable" class="token-list">
        <v-list-item
          v-for="t in tokens"
          :key="t.id"
          :title="t.name"
          :subtitle="tokenSubtitle(t)"
        >
          <template #prepend>
            <v-avatar color="surface-variant" size="32" rounded>
              <v-icon icon="mdi-key" size="16" />
            </v-avatar>
          </template>
          <template #append>
            <v-tooltip text="Revoke this token" location="top">
              <template #activator="{ props: tipProps }">
                <v-btn
                  v-bind="tipProps"
                  icon="mdi-delete-outline"
                  size="small"
                  variant="text"
                  color="error"
                  @click="revoke(t)"
                />
              </template>
            </v-tooltip>
          </template>
        </v-list-item>
      </v-list>
    </v-card>

    <v-card variant="outlined" class="mcp-card mb-6">
      <div class="mcp-card__header">
        <v-icon icon="mdi-toolbox-outline" size="18" color="primary" />
        <div class="text-subtitle-2 font-weight-medium">Available tools</div>
      </div>
      <div class="mcp-card__body">
        <div v-for="group in TOOL_GROUPS" :key="group.label" class="tool-group">
          <div class="tool-group__label">
            <v-chip
              :color="group.label === 'Write' ? 'warning' : 'success'"
              size="x-small"
              variant="tonal"
              class="text-uppercase font-weight-bold"
            >
              {{ group.label }}
            </v-chip>
            <span class="text-caption text-medium-emphasis">
              {{ group.label === 'Write' ? 'Mutates org state' : 'Read-only' }}
            </span>
          </div>
          <div
            v-for="tool in group.tools"
            :key="tool.name"
            class="tool-row"
          >
            <code class="tool-row__name">{{ tool.name }}</code>
            <div class="tool-row__description">{{ tool.description }}</div>
          </div>
        </div>
      </div>
      <AppCallout
        variant="info"
        eyebrow="Writes are bounded"
        icon="mdi-shield-check-outline"
        class="mx-4 mb-4"
      >
        <code class="inline-code">update_bud</code> is restricted to
        three creative phases:
        <code class="inline-code">requirements_md</code> in BUD,
        <code class="inline-code">design</code> wireframe HTML in DESIGN,
        and <code class="inline-code">tech_spec_md</code> in TECH_ARCH.
        Testing and Code Review remain UI / agent-driven. Every write
        snapshots prior state in the BUD detail's History tab so a bad
        edit reverts in one click.
      </AppCallout>
    </v-card>

    <v-card variant="outlined" class="mcp-card mb-6">
      <div class="mcp-card__header">
        <v-icon icon="mdi-code-braces" size="18" color="primary" />
        <div class="text-subtitle-2 font-weight-medium">Client config snippets</div>
      </div>
      <v-tabs v-model="snippetTab" density="compact" class="px-4">
        <v-tab v-for="(snippet, key) in SNIPPETS" :key="key" :value="key">
          {{ snippet.label }}
        </v-tab>
      </v-tabs>
      <v-divider />
      <v-window v-model="snippetTab">
        <v-window-item v-for="(snippet, key) in SNIPPETS" :key="key" :value="key">
          <div class="snippet-block">
            <pre class="snippet-pre">{{ snippet.render(endpointUrl) }}</pre>
            <v-btn
              class="snippet-copy"
              size="small"
              variant="tonal"
              prepend-icon="mdi-content-copy"
              @click="copy(snippet.render(endpointUrl), 'Snippet copied')"
            >
              Copy snippet
            </v-btn>
          </div>
        </v-window-item>
      </v-window>
      <AppCallout variant="warning" eyebrow="Trust boundary" class="mx-4 mb-4">
        Connecting an external LLM extends its trust boundary to your
        BUD content. Anyone who can read a token can read every BUD in
        your org. Treat tokens like passwords; revoke unused ones.
      </AppCallout>
    </v-card>

    <!-- Example starter prompts. The point of MCP isn't just "your AI can
         now read our data" — it's that your AI can use the SAME prompts
         our agents use. These snippets give the local LLM the verbs it
         needs (which tools to call, in what order) so the output lands
         in the shape the BUD section editors expect. -->
    <v-card variant="outlined" class="mcp-card mb-6">
      <div class="mcp-card__header">
        <v-icon icon="mdi-text-box-edit-outline" size="18" color="primary" />
        <div class="text-subtitle-2 font-weight-medium">Example prompts to start work</div>
      </div>
      <div class="mcp-card__body pb-0">
        <div class="text-caption text-medium-emphasis">
          Paste one of these into your local AI to kick off a phase. Each
          tells the LLM to fetch our agent's exact prompt via
          <code class="inline-code">get_prompt</code>, gather context, draft
          the content, and then call
          <code class="inline-code">create_bud</code> /
          <code class="inline-code">update_bud</code> only after you confirm
          the draft — no writes on intermediate edits.
        </div>
      </div>
      <div class="prompt-tab-row">
        <v-tabs v-model="exampleTab" density="compact" class="prompt-tab-row__tabs">
          <v-tab v-for="(ex, key) in EXAMPLE_PROMPTS" :key="key" :value="key">
            {{ ex.label }}
          </v-tab>
        </v-tabs>
        <AppPillToggle
          v-if="showPromptModeToggle"
          v-model="promptMode"
          :options="promptModeOptions"
        />
      </div>
      <v-divider />
      <v-window v-model="exampleTab">
        <v-window-item v-for="(ex, key) in EXAMPLE_PROMPTS" :key="key" :value="key">
          <div class="snippet-block">
            <pre class="snippet-pre">{{ promptBody(ex) }}</pre>
            <v-btn
              class="snippet-copy"
              size="small"
              variant="tonal"
              prepend-icon="mdi-content-copy"
              @click="copy(promptBody(ex), 'Prompt copied')"
            >
              Copy prompt
            </v-btn>
          </div>
        </v-window-item>
      </v-window>
      <AppCallout variant="info" eyebrow="Placeholders" class="mx-4 mb-4">
        Replace <code class="inline-code">&lt;your topic&gt;</code>,
        <code class="inline-code">&lt;BUD-NUMBER&gt;</code>, and
        <code class="inline-code">&lt;uuid&gt;</code> before sending. The
        Design and Tech-spec prompts need the BUD UUID — grab it from the
        URL on the BUD detail page or call
        <code class="inline-code">get_bud_context()</code> and look up by
        <code class="inline-code">bud_number</code>.
      </AppCallout>
    </v-card>

    <!-- Create-token dialog -->
    <v-dialog v-model="showCreate" max-width="460" @update:model-value="onCreateDialogToggle">
      <v-card class="pa-5">
        <div class="text-h6 font-weight-bold mb-3">New MCP token</div>
        <v-text-field
          v-model="newName"
          label="Token name"
          placeholder="e.g. claude-desktop"
          :rules="[(v) => !!v?.trim() || 'Name required']"
          autofocus
          density="comfortable"
          :error-messages="createError ? [createError] : []"
          @update:model-value="createError = null"
        />
        <v-text-field
          v-model.number="newTTL"
          type="number"
          label="Expires in (days)"
          :min="1"
          :max="365"
          density="comfortable"
          hint="1–365 days. Default 90."
          persistent-hint
        />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showCreate = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="creating"
            :disabled="!newName.trim()"
            @click="createToken"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="2000"
      location="bottom"
    >
      {{ snackbar.text }}
    </v-snackbar>

    <!-- Plaintext-once dialog -->
    <v-dialog v-model="plaintextDialog" max-width="560" persistent>
      <v-card class="pa-5">
        <div class="text-h6 font-weight-bold mb-3">
          <v-icon icon="mdi-shield-key" class="mr-1" />
          Token created — copy it now
        </div>
        <p class="text-body-2 text-medium-emphasis mb-3">
          This is the only time we will show this token. Once you close
          this dialog the plaintext is gone — we only keep a bcrypt hash.
        </p>
        <v-text-field
          :model-value="plaintextToken"
          readonly
          density="comfortable"
          append-inner-icon="mdi-content-copy"
          @click:append-inner="copy(plaintextToken, 'Token copied successfully')"
        />
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="closePlaintext">I have copied it</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'

interface TokenRead {
  id: string
  name: string
  token_prefix: string
  expires_at: string | null
  last_used_at: string | null
  created_at: string
}

const tokens = ref<TokenRead[]>([])
const loading = ref(false)

const showCreate = ref(false)
const newName = ref('')
const newTTL = ref(90)
const creating = ref(false)

const plaintextDialog = ref(false)
const plaintextToken = ref('')

// snippetTab / exampleTab refs are declared further down the file —
// after the SNIPPETS / EXAMPLE_PROMPTS constants — so the initial
// value can derive from Object.keys() without hitting the TDZ.

const endpointUrl = computed(() => {
  // VITE_API_BASE_URL may be absolute ("https://api.example.com" or
  // "https://api.example.com/api") for split-host deployments, OR a
  // bare path like "/api" when the SPA and API share an origin behind
  // the same proxy. After stripping a trailing "/api" the path-form
  // collapses to "" — fall back to window.location.origin in that case
  // so the user sees a full URL instead of "/mcp/sse".
  const stripped = (import.meta.env.VITE_API_BASE_URL ?? '')
    .replace(/\/api\/?$/, '')
    .replace(/\/$/, '')
  const base = /^https?:\/\//i.test(stripped) ? stripped : window.location.origin
  return `${base}/mcp/sse`
})

// Grouped so users can see at a glance which tools mutate org state
// and which don't. Names + descriptions match the backend's
// _REMOTE_TOOL_SCHEMAS in app/mcp/streamable.py — keep in sync.
const TOOL_GROUPS: { label: string; tools: { name: string; description: string }[] }[] = [
  {
    label: 'Read',
    tools: [
      { name: 'get_bud_context', description: 'List in-progress BUDs (with optional keyword filter) so the LLM doesn\'t propose duplicates.' },
      { name: 'get_bud_by_id', description: 'Fetch one BUD by UUID with the full body of every section.' },
      { name: 'get_features', description: 'Hybrid keyword + semantic search over your org\'s active features.' },
      { name: 'list_design_systems', description: 'Design-system metadata per repo.' },
      { name: 'get_design_system', description: 'Full HTML/CSS/tokens for a repo or the org default.' },
      { name: 'get_prompt', description: 'Return our agent\'s prompt for a stage (task_type: pm / design / tech_plan / testing) so your local AI produces matching output.' },
    ],
  },
  {
    label: 'Write',
    tools: [
      { name: 'create_bud', description: 'Create a new BUD; the calling token\'s user is set as both creator and assignee.' },
      { name: 'update_bud', description: 'Update the content field owned by the BUD\'s current phase. Assignee-only; the server picks the editable field from the phase.' },
    ],
  },
]

interface ClientSnippet {
  label: string
  render: (url: string) => string
}

// PM/PRD genuinely has two distinct flows — create_bud for a new
// BUD vs update_bud to revise an existing one. Design and Tech-spec
// only ever call update_bud (the BUD already exists), so the
// "Create / Update" framing is misleading on those tabs and a
// single prompt covers both first-time writes and refinements.
interface ExamplePromptWithToggle {
  kind: 'with-toggle'
  label: string
  create: string
  update: string
}

interface ExamplePromptSingle {
  kind: 'single'
  label: string
  body: string
}

type ExamplePrompt = ExamplePromptWithToggle | ExamplePromptSingle

type PromptMode = 'create' | 'update'

// Starter prompts for each BUD phase. Designed to be pasted verbatim
// into the local LLM after the MCP server is connected. Each one (a)
// pulls our agent's own prompt via get_prompt so the output shape
// matches the section editor, (b) lists the read-only tools the LLM
// should call to gather context, and (c) tells the user where to paste
// the result. Keep these short and copy-pasteable — long prose here
// dilutes the verbs the LLM needs to act on.
// Shared "review then commit" gate inserted at the end of every
// prompt. Stops the LLM from writing on every micro-edit during
// iteration — users want to review the full draft once before
// anything lands in the DB, and they want subsequent rounds of "tweak
// this paragraph" to stay in the chat until they're done.
const REVIEW_GATE = `Important — review-then-commit:
* Compose the full draft and show it to me in the chat.
* Wait for me to say "create it" / "update it" / "looks good, save it"
  (or words to that effect). Do NOT call create_bud / update_bud
  before that explicit confirmation.
* If I ask for changes, iterate on the draft IN THE CHAT — no MCP
  writes mid-iteration.
* Once I confirm, make the single write, show me the server response,
  and stop. Don't keep editing afterwards unless I ask.`

const EXAMPLE_PROMPTS: Record<string, ExamplePrompt> = {
  pm: {
    kind: 'with-toggle',
    label: 'PM / PRD',
    create: `I want to create a BUD for: <your topic>

Use the bodhiorchard MCP server I've connected. Steps:
1. Call get_prompt(task_type="pm") and follow that prompt EXACTLY for
   the body shape.
2. Call get_bud_context() to see what's already in flight — refuse to
   continue if my topic is an obvious duplicate (tell me the BUD-id
   instead).
3. Call get_features(query="<keywords from my topic>") and paginate
   (offset += limit while has_more) until you've reviewed the relevant
   matches. Note the feature IDs of anything this PRD will touch.
4. Compose the title and the full Markdown body. Do NOT embed a
   trailing JSON fence — pass linked feature UUIDs via the explicit
   parameter instead.

${REVIEW_GATE}

When I confirm, call create_bud(title=<title>, requirements_md=<full
body>, linked_feature_ids=[<feature-uuid>, ...]). Show me bud_number,
id, and linked_features.linked_count from the response.`,
    update: `I want to update the PRD for BUD-<BUD-NUMBER>.

1. Call get_bud_by_id(bud_id="<uuid>") and validate:
   * 'status' == "bud". If not, stop and tell me what status the
     BUD is actually in.
   * 'is_assignee' == true. If false, stop and tell me which user
     ID owns it — only the assignee can update via MCP.
   Do NOT proceed past these checks if either fails.
2. Call get_prompt(task_type="pm") to recall the body shape we expect.
3. Optionally call get_features for new areas the revision touches.
4. Compose the FULL revised Markdown body (not a diff — update_bud
   replaces the field).

${REVIEW_GATE}

When I confirm, call update_bud(bud_id="<uuid>", content=<full body>,
expected_phase="bud", linked_feature_ids=[<feature-uuid>, ...]). Show
me the response. If the server returns phase_mismatch, the BUD moved
since your pre-flight read — refetch and reconsider before retrying.`,
  },
  design: {
    kind: 'single',
    label: 'Design',
    body: `I want to write or revise the UX/UI design for BUD-<BUD-NUMBER>.

The BUD already exists — the design is added by calling update_bud
while the BUD is in the DESIGN phase. There is no separate "create
design" tool; if the design row is empty this still uses update_bud,
and 'create_bud' is reserved for brand-new BUDs in the BUD phase.

1. Call get_bud_by_id(bud_id="<uuid>") and validate:
   * 'status' == "design". If not, stop and tell me what status
     the BUD is actually in (design content can only be written while
     the BUD is in the design phase).
   * 'is_assignee' == true. If false, stop and tell me which user
     ID owns it — only the assignee can update via MCP.
   Do NOT proceed past these checks if either fails.
2. Call get_bud_designs(bud_id="<uuid>") to see if a wireframe already
   exists. If so, you're refining it — preserve structure / tokens
   the user already approved. If empty, this is the first wireframe.
3. Call get_prompt(task_type="design") and follow that prompt EXACTLY
   for the wireframe HTML shape.
4. Call list_design_systems(), then get_design_system(repo_id="<id>")
   for the repo this design lands in (or omit repo_id for the org
   default). Use ONLY tokens/components from that design system — no
   ad-hoc colours, no new components.
5. Compose the FULL wireframe HTML (update_bud overwrites the field).

${REVIEW_GATE}

When I confirm, call update_bud(bud_id="<uuid>", content=<wireframe
HTML>, expected_phase="design"). The expected_phase param is the
safety net — if the BUD moved out of DESIGN since your pre-flight
read, the server returns phase_mismatch instead of writing your HTML
into the wrong section. Show me the response.`,
  },
  tech_arch: {
    kind: 'single',
    label: 'Tech spec',
    body: `I want to write or revise the tech architecture for BUD-<BUD-NUMBER>.

The BUD already exists — the tech spec is added by calling update_bud
while the BUD is in the TECH_ARCH phase. There is no separate "create
tech spec" tool; 'create_bud' is reserved for brand-new BUDs in the
BUD phase.

1. Call get_bud_by_id(bud_id="<uuid>") and validate:
   * 'status' == "tech_arch". If not, stop and tell me what status
     the BUD is actually in (tech_spec can only be written while the
     BUD is in the tech_arch phase).
   * 'is_assignee' == true. If false, stop and tell me which user
     ID owns it — only the assignee can update via MCP.
   Also note whether 'tech_spec_md' is already populated — if so,
   preserve structure when you revise; if empty, this is the first
   spec. Do NOT proceed past the status / assignee checks if either
   fails.
2. Call get_prompt(task_type="tech_plan") and follow that prompt
   EXACTLY for the spec shape.
3. Call get_features(query="<area touched by this BUD>") with
   pagination to see existing capabilities you should reuse or extend
   rather than re-implement.
4. Compose the FULL tech-spec Markdown (update_bud replaces the
   field). Use explicit sections for: components touched, schema
   changes, API surface, testing strategy, rollout & rollback. End
   the body with the impacted-repos JSON fence the prompt describes
   — the backend parses it.

${REVIEW_GATE}

When I confirm, call update_bud(bud_id="<uuid>", content=<tech spec
markdown>, expected_phase="tech_arch", linked_feature_ids=[<feature-uuid>,
...]). The expected_phase param is the safety net — if the BUD moved
out of TECH_ARCH since your pre-flight read, the server returns
phase_mismatch instead of writing your tech spec into the wrong
section. Show me the response (id, bud_number, field, phase,
linked_features).`,
  },
}

// Desktop clients' mcp.json schemas reject ``"transport": "streamable-http"``
// directly (it's the MCP wire-protocol identifier, not a config-file key).
// The cross-version reliable shape is the ``mcp-remote`` npm bridge — it
// runs stdio to the client and translates to our streamable-http endpoint.
// Newer Claude Desktop builds support a native ``"type": "http"`` form, but
// mcp-remote works everywhere; recommend it as the default snippet.
const SNIPPETS: Record<string, ClientSnippet> = {
  'claude-desktop': {
    label: 'Claude Desktop',
    render: (url) => `// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "bodhiorchard": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "${url}",
        "--header",
        "Authorization: Bearer YOUR_TOKEN_HERE"
      ]
    }
  }
}`,
  },
  'cursor': {
    label: 'Cursor',
    render: (url) => `// ~/.cursor/mcp.json
{
  "mcpServers": {
    "bodhiorchard": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "${url}",
        "--header",
        "Authorization: Bearer YOUR_TOKEN_HERE"
      ]
    }
  }
}`,
  },
  'continue': {
    label: 'Continue',
    render: (url) => `// ~/.continue/config.json — under "experimental.mcpServers"
{
  "name": "bodhiorchard",
  "command": "npx",
  "args": [
    "-y",
    "mcp-remote",
    "${url}",
    "--header",
    "Authorization: Bearer YOUR_TOKEN_HERE"
  ]
}`,
  },
}

// Initialise from Object.keys so renaming a SNIPPETS / EXAMPLE_PROMPTS
// key can't silently render a blank v-window — v-tabs requires its
// model to match one of the rendered v-tab :value props.
const snippetTab = ref<string>(Object.keys(SNIPPETS)[0] ?? '')
const exampleTab = ref<string>(Object.keys(EXAMPLE_PROMPTS)[0] ?? '')

// Sub-toggle inside each Example tab. ``create`` is the first-time
// write (new BUD or empty section); ``update`` is the "I already
// have content, refine it" flow that should read existing state
// before composing the diff.
const promptMode = ref<PromptMode>('create')
const promptModeOptions: { label: string; value: PromptMode }[] = [
  { label: 'Create', value: 'create' },
  { label: 'Update', value: 'update' },
]

function promptBody(ex: ExamplePrompt): string {
  if (ex.kind === 'single') return ex.body
  return promptMode.value === 'update' ? ex.update : ex.create
}

// The Create/Update toggle is only meaningful when the active tab has
// two distinct flows. Design + Tech-spec only ever call update_bud,
// so showing the toggle there would suggest a Create path that
// doesn't exist.
const activePrompt = computed<ExamplePrompt | undefined>(
  () => EXAMPLE_PROMPTS[exampleTab.value],
)
const showPromptModeToggle = computed(() => activePrompt.value?.kind === 'with-toggle')

function tokenSubtitle(t: TokenRead): string {
  const parts: string[] = [`Prefix ${t.token_prefix}…`]
  if (t.expires_at) {
    parts.push(`Expires ${formatDate(t.expires_at)}`)
  } else {
    parts.push('No expiry')
  }
  parts.push(t.last_used_at ? `Last used ${formatDate(t.last_used_at)}` : 'Never used')
  return parts.join(' · ')
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

async function refresh(): Promise<void> {
  loading.value = true
  try {
    const { data } = await api.get<TokenRead[]>('/v1/me/mcp-tokens')
    tokens.value = data
  } finally {
    loading.value = false
  }
}

// Inline error for the New-token dialog. Cleared on every field edit
// and on dialog open/close so it never stays stale across attempts.
const createError = ref<string | null>(null)

function onCreateDialogToggle(open: boolean): void {
  if (!open) {
    createError.value = null
  }
}

async function createToken(): Promise<void> {
  creating.value = true
  createError.value = null
  try {
    const { data } = await api.post<{ mcp_token: string; name: string }>(
      '/v1/me/mcp-tokens',
      { name: newName.value.trim(), expires_in_days: newTTL.value },
    )
    plaintextToken.value = data.mcp_token
    plaintextDialog.value = true
    showCreate.value = false
    newName.value = ''
    newTTL.value = 90
    await refresh()
  } catch (err: unknown) {
    // Show the backend's ``detail`` message inline on the Token-name
    // field. The most common failure is the 409 duplicate-name from
    // ``POST /me/mcp-tokens`` (see backend/app/api/v1/me.py); other
    // statuses fall back to a generic message so the user always sees
    // SOMETHING rather than the dialog appearing to silently no-op.
    const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
    const detail = axiosErr.response?.data?.detail
    if (axiosErr.response?.status === 409) {
      createError.value = detail || 'A token with that name already exists.'
    } else if (typeof detail === 'string') {
      createError.value = detail
    } else {
      createError.value = 'Could not create token. Please try again.'
    }
  } finally {
    creating.value = false
  }
}

function closePlaintext(): void {
  plaintextDialog.value = false
  plaintextToken.value = ''
}

async function revoke(t: TokenRead): Promise<void> {
  if (!confirm(`Revoke token "${t.name}"? Any client using it will be locked out immediately.`)) {
    return
  }
  await api.delete(`/v1/me/mcp-tokens/${t.id}`)
  await refresh()
}

const snackbar = ref<{ show: boolean; text: string; color: 'success' | 'error' }>({
  show: false,
  text: '',
  color: 'success',
})

function notify(text: string, color: 'success' | 'error' = 'success'): void {
  snackbar.value = { show: true, text, color }
}

async function copy(text: string, label = 'Copied to clipboard'): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    notify(label, 'success')
  } catch {
    // Clipboard write blocked (insecure context, denied permission) —
    // surface the failure so the user knows to fall back to manual
    // select rather than silently doing nothing.
    notify('Copy failed — select and copy manually', 'error')
  }
}

onMounted(refresh)
</script>

<style scoped>
.mcp-page {
  max-width: 1040px;
  margin: 0 auto;
}
.mcp-hero__eyebrow {
  letter-spacing: 0.08em;
}
.mcp-hero__lede {
  max-width: 78ch;
  line-height: 1.55;
}
.mcp-card {
  overflow: hidden;
}
.mcp-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  background: rgba(var(--v-theme-on-surface), 0.025);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
.mcp-card__body {
  padding: 18px;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px 16px;
}
.token-list {
  background: transparent;
}
.endpoint-code {
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 8px 14px;
  border-radius: 6px;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  font-size: 13px;
  min-width: 0;
  word-break: break-all;
}
.inline-code {
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.85em;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
}
.tool-group + .tool-group {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.08);
}
.tool-group__label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.tool-row {
  display: grid;
  grid-template-columns: minmax(160px, max-content) 1fr;
  align-items: baseline;
  gap: 14px;
  padding: 6px 0;
}
.tool-row__name {
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 2px 8px;
  border-radius: 4px;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
}
.tool-row__description {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.78);
}
.snippet-block {
  position: relative;
  padding: 16px 18px 18px;
}
.snippet-copy {
  position: absolute;
  top: 24px;
  right: 26px;
}
.snippet-pre {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 8px;
  padding: 14px 16px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  white-space: pre;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
@media (max-width: 600px) {
  .tool-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .snippet-copy {
    position: static;
    margin-top: 8px;
  }
}

/* Row containing the phase tabs (left) and the create/update toggle
   (right). Symmetric inset so the toggle has the same breathing room
   from the card edge that the tabs have on their side, and the row
   has top + bottom padding so it doesn't crash into the prose above
   or the divider below. */
.prompt-tab-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px 12px;
  flex-wrap: wrap;
}
.prompt-tab-row__tabs {
  min-width: 0;
}

@media (max-width: 560px) {
  .prompt-tab-row {
    padding: 12px 16px;
  }
}
</style>
