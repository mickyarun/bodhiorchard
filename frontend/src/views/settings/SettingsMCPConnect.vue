<!-- BYO-AI MCP connect panel. Users can mint scoped named tokens here
     and copy the mcp.json snippet for their local AI client (Claude
     Desktop, Cursor, Continue) so it can read BUD context, search the
     org's knowledge, and consult design systems while drafting PRD /
     design / tech-spec content. -->
<template>
  <v-container fluid class="pa-6" style="max-width: 960px">
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon icon="mdi-connection" size="28" />
      <h1 class="text-h5 font-weight-bold">Connect your local AI (MCP)</h1>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-6">
      When auto-generate is off on a BUD, your own local AI assistant
      can use the four read-only tools below to gather context before
      you paste the finished PRD / design / tech spec into the editor.
      Token credentials are personal and revocable at any time.
    </p>

    <v-card variant="outlined" class="mb-6 pa-4">
      <div class="text-subtitle-1 font-weight-medium mb-2">Endpoint</div>
      <div class="d-flex align-center ga-2">
        <code class="endpoint-code">{{ endpointUrl }}</code>
        <v-btn icon="mdi-content-copy" size="small" variant="text" @click="copy(endpointUrl)" />
      </div>
      <div class="text-caption text-medium-emphasis mt-2">
        Send <code>Authorization: Bearer &lt;token&gt;</code> on every request.
        Stream uses MCP <code>2025-03-26/streamable-http</code>.
      </div>
    </v-card>

    <v-card variant="outlined" class="mb-6">
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-key-variant" />
        Your tokens
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
      </v-card-title>
      <v-divider />
      <v-list lines="two">
        <v-list-item v-if="!tokens.length && !loading">
          <v-list-item-title class="text-medium-emphasis">
            No tokens yet — create one to connect your local AI.
          </v-list-item-title>
        </v-list-item>
        <v-list-item
          v-for="t in tokens"
          :key="t.id"
          :title="t.name"
          :subtitle="tokenSubtitle(t)"
        >
          <template #append>
            <v-btn
              icon="mdi-delete-outline"
              size="small"
              variant="text"
              color="error"
              @click="revoke(t)"
            />
          </template>
        </v-list-item>
      </v-list>
    </v-card>

    <v-card variant="outlined" class="mb-6 pa-4">
      <div class="text-subtitle-1 font-weight-medium mb-3">Available tools (read-only)</div>
      <div v-for="tool in TOOL_CATALOGUE" :key="tool.name" class="mb-2">
        <code class="text-caption font-weight-bold">{{ tool.name }}</code>
        — <span class="text-caption">{{ tool.description }}</span>
      </div>
      <v-alert type="info" variant="tonal" density="compact" class="mt-4">
        <strong>Write-back is NOT exposed remotely.</strong> When the local AI
        finishes drafting, paste the result into the BUD section editor.
        This intentional limit keeps a leaked or prompt-injected token
        from rewriting your BUDs.
      </v-alert>
    </v-card>

    <v-card variant="outlined" class="mb-6 pa-4">
      <div class="text-subtitle-1 font-weight-medium mb-3">Client config snippets</div>
      <v-tabs v-model="snippetTab" density="compact">
        <v-tab v-for="(snippet, key) in SNIPPETS" :key="key" :value="key">{{ snippet.label }}</v-tab>
      </v-tabs>
      <v-window v-model="snippetTab" class="mt-3">
        <v-window-item v-for="(snippet, key) in SNIPPETS" :key="key" :value="key">
          <pre class="snippet-pre">{{ snippet.render(endpointUrl) }}</pre>
          <div class="d-flex justify-end">
            <v-btn
              size="small"
              variant="text"
              prepend-icon="mdi-content-copy"
              @click="copy(snippet.render(endpointUrl))"
            >
              Copy snippet
            </v-btn>
          </div>
        </v-window-item>
      </v-window>
      <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
        Connecting an external LLM extends its trust boundary to your BUD
        content. Anyone who can read a token can read every BUD in your
        org. Treat tokens like passwords; revoke unused ones.
      </v-alert>
    </v-card>

    <!-- Example starter prompts. The point of MCP isn't just "your AI can
         now read our data" — it's that your AI can use the SAME prompts
         our agents use. These snippets give the local LLM the verbs it
         needs (which tools to call, in what order) so the output lands
         in the shape the BUD section editors expect. -->
    <v-card variant="outlined" class="mb-6 pa-4">
      <div class="text-subtitle-1 font-weight-medium mb-2">Example prompts to start work</div>
      <div class="text-caption text-medium-emphasis mb-3">
        Paste one of these into your local AI to kick off a phase. Each
        instructs the LLM to fetch our exact agent prompt via
        <code>get_prompt</code>, gather the right context, then produce
        the section's content. When it's done, copy the body into the
        matching BUD editor tab.
      </div>
      <v-tabs v-model="exampleTab" density="compact">
        <v-tab v-for="(ex, key) in EXAMPLE_PROMPTS" :key="key" :value="key">
          {{ ex.label }}
        </v-tab>
      </v-tabs>
      <v-window v-model="exampleTab" class="mt-3">
        <v-window-item v-for="(ex, key) in EXAMPLE_PROMPTS" :key="key" :value="key">
          <pre class="snippet-pre">{{ ex.body }}</pre>
          <div class="d-flex justify-end">
            <v-btn
              size="small"
              variant="text"
              prepend-icon="mdi-content-copy"
              @click="copy(ex.body)"
            >
              Copy prompt
            </v-btn>
          </div>
        </v-window-item>
      </v-window>
      <v-alert type="info" variant="tonal" density="compact" class="mt-3">
        Replace <code>&lt;your topic&gt;</code> / <code>&lt;BUD-NUMBER&gt;</code>
        in the prompt with the actual values before sending. The LLM
        will call the read-only tools listed above; you save the
        result by pasting into the BUD editor.
      </v-alert>
    </v-card>

    <!-- Create-token dialog -->
    <v-dialog v-model="showCreate" max-width="460">
      <v-card class="pa-5">
        <div class="text-h6 font-weight-bold mb-3">New MCP token</div>
        <v-text-field
          v-model="newName"
          label="Token name"
          placeholder="e.g. claude-desktop"
          :rules="[(v) => !!v?.trim() || 'Name required']"
          autofocus
          density="comfortable"
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
          @click:append-inner="copy(plaintextToken)"
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

const snippetTab = ref<string>('claude-desktop')
const exampleTab = ref<string>('pm')

const endpointUrl = computed(() => {
  // Prefer VITE_API_BASE_URL when set (split-host deployments); otherwise
  // assume the API and the SPA share an origin and the user can hand-edit
  // the snippet if Caddy maps a different public hostname.
  const base = (import.meta.env.VITE_API_BASE_URL ?? window.location.origin)
    .replace(/\/api\/?$/, '')
    .replace(/\/$/, '')
  return `${base}/mcp/sse`
})

const TOOL_CATALOGUE = [
  { name: 'get_bud_context', description: 'List recent BUDs for context.' },
  { name: 'get_features', description: 'Semantic knowledge search over your org\'s active features.' },
  { name: 'list_design_systems', description: 'Design-system metadata per repo.' },
  { name: 'get_design_system', description: 'Full HTML/CSS/tokens for a repo or the org default.' },
  { name: 'get_prompt', description: 'Return our agent\'s prompt for a stage (task_type: bud / design / tech_arch / testing) so your local AI produces matching output.' },
]

interface ClientSnippet {
  label: string
  render: (url: string) => string
}

interface ExamplePrompt {
  label: string
  body: string
}

// Starter prompts for each BUD phase. Designed to be pasted verbatim
// into the local LLM after the MCP server is connected. Each one (a)
// pulls our agent's own prompt via get_prompt so the output shape
// matches the section editor, (b) lists the read-only tools the LLM
// should call to gather context, and (c) tells the user where to paste
// the result. Keep these short and copy-pasteable — long prose here
// dilutes the verbs the LLM needs to act on.
const EXAMPLE_PROMPTS: Record<string, ExamplePrompt> = {
  pm: {
    label: 'PM / PRD',
    body: `I want to draft a PRD for: <your topic>

Use the bodhiorchard MCP server I've connected. Steps:
1. Call get_prompt(task_type="bud") and follow that prompt EXACTLY.
2. Call get_bud_context() to see what's already in flight so you don't
   propose a duplicate.
3. Call get_features(query="<keywords from my topic>") and paginate
   (offset += limit while has_more) until you've reviewed the relevant
   matches. Note the feature IDs of anything this PRD will touch.
4. Produce the Markdown body the prompt asks for. End with the
   trailing JSON fence: \`\`\`json
   {"linked_feature_ids": ["<feature-uuid>", ...]}
   \`\`\`
   so when I paste this into the BUD's requirements editor, the
   linked-features will auto-populate.

When done, give me ONLY the final Markdown — I'll paste it into the
BUD's "Requirements" tab.`,
  },
  design: {
    label: 'Design',
    body: `I want to draft the UX/UI design for BUD-<BUD-NUMBER>.

Use the bodhiorchard MCP server. Steps:
1. Call get_prompt(task_type="design") and follow that prompt EXACTLY.
2. Call get_bud_context() (then read the requirements_md for the BUD
   you're working on) so the design ties to the agreed PRD.
3. Call list_design_systems(), then get_design_system(repo_id="<id>")
   for the repo this design lands in (or omit repo_id for the org
   default). Use ONLY tokens/components from that design system — no
   ad-hoc colours, no new components.
4. Produce the wireframe HTML the prompt asks for.

When done, give me ONLY the final HTML — I'll paste it into the BUD's
"Design" tab.`,
  },
  tech_arch: {
    label: 'Tech spec',
    body: `I want to write the tech architecture for BUD-<BUD-NUMBER>.

Use the bodhiorchard MCP server. Steps:
1. Call get_prompt(task_type="tech_arch") and follow that prompt
   EXACTLY.
2. Call get_bud_context() and use the PRD content for the BUD as the
   authoritative scope — don't invent requirements.
3. Call get_features(query="<area touched by this BUD>") with
   pagination to see what existing capabilities you should reuse or
   extend rather than re-implement.
4. Produce the tech-spec Markdown the prompt asks for, with explicit
   sections for: components touched, schema changes, API surface,
   testing strategy, rollout & rollback.

When done, give me ONLY the final Markdown — I'll paste it into the
BUD's "Tech spec" tab.`,
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

async function createToken(): Promise<void> {
  creating.value = true
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

async function copy(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Clipboard write is best-effort; user can fall back to manual select.
  }
}

onMounted(refresh)
</script>

<style scoped>
.endpoint-code {
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 4px 10px;
  border-radius: 4px;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
}
.snippet-pre {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.4;
  font-family: var(--v-font-family-monospace, 'Menlo', monospace);
  white-space: pre;
}
</style>
