<template>
  <div class="lifecycle-flow">
    <!-- Main horizontal track -->
    <div class="flow-track">
      <template v-for="(node, i) in mainFlow" :key="node.id">
        <div
          class="flow-node"
          :class="{
            'flow-node--decision': node.decision,
            'flow-node--target': node.loopTarget,
          }"
        >
          <div
            class="flow-node__icon"
            :class="node.decision ? 'flow-node__icon--diamond' : ''"
            :style="{ '--node-color': `var(--v-theme-${node.color})` }"
          >
            <v-icon :icon="node.icon" :size="node.decision ? 14 : 16" />
          </div>
          <div class="flow-node__label">{{ node.label }}</div>
          <div class="flow-node__agent">{{ node.agent }}</div>
        </div>
        <div v-if="i < mainFlow.length - 1" class="flow-arrow">
          <div class="flow-arrow__line" />
          <div class="flow-arrow__head" />
          <span v-if="node.arrowLabel" class="flow-arrow__label">{{ node.arrowLabel }}</span>
        </div>
      </template>
    </div>

    <!-- Loop-back paths -->
    <div class="flow-loops">
      <div class="flow-loop flow-loop--1">
        <div class="flow-loop__bar" />
        <div class="flow-loop__content">
          <v-icon icon="mdi-arrow-left-bold" size="14" color="error" />
          <v-chip size="x-small" color="error" variant="tonal" class="mx-1">Yes: Bugs &gt; threshold</v-chip>
          <span class="text-caption"><strong>Reassign Agent</strong> — Dev → bug review, QA → next PRD</span>
          <v-icon icon="mdi-arrow-up-bold" size="14" color="error" class="ml-1" />
          <span class="text-caption text-medium-emphasis">back to Dev</span>
        </div>
      </div>
      <div class="flow-loop flow-loop--2">
        <div class="flow-loop__bar" />
        <div class="flow-loop__content">
          <v-icon icon="mdi-arrow-left-bold" size="14" color="warning" />
          <v-chip size="x-small" color="warning" variant="tonal" class="mx-1">Yes: Post-deploy bug</v-chip>
          <span class="text-caption"><strong>Reopen PRD</strong> — Auto-classify bug type → back to Dev</span>
        </div>
      </div>
    </div>

    <!-- Feedback arc -->
    <div class="flow-feedback">
      <div class="flow-feedback__line" />
      <div class="flow-feedback__content">
        <v-icon icon="mdi-refresh" size="14" color="primary" class="mr-1" />
        <span class="text-caption text-medium-emphasis">
          Learning feeds back into Triage — predictions improve with every cycle
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface FlowNode {
  id: string
  icon: string
  label: string
  agent: string
  color: string
  decision?: boolean
  loopTarget?: boolean
  arrowLabel?: string
}

const mainFlow: FlowNode[] = [
  {
    id: 'intake',
    icon: 'mdi-chat-outline',
    label: 'Chat Intake',
    agent: 'Triage Agent',
    color: 'primary',
  },
  {
    id: 'prd',
    icon: 'mdi-file-document-edit-outline',
    label: 'PRD Generation',
    agent: 'PRD Agent',
    color: 'secondary',
  },
  {
    id: 'design',
    icon: 'mdi-palette-outline',
    label: 'Design',
    agent: 'Design Phase',
    color: 'primary',
  },
  {
    id: 'dev',
    icon: 'mdi-code-braces',
    label: 'Development',
    agent: 'AI + Human',
    color: 'primary',
    loopTarget: true,
  },
  {
    id: 'test',
    icon: 'mdi-test-tube',
    label: 'Auto Test Gen',
    agent: 'Test Generation',
    color: 'secondary',
  },
  {
    id: 'qa',
    icon: 'mdi-clipboard-check-outline',
    label: 'QA & UAT',
    agent: 'Bug Linker Agent',
    color: 'primary',
  },
  {
    id: 'bug-decision',
    icon: 'mdi-bug-outline',
    label: 'Bugs > threshold?',
    agent: 'Bug Linker',
    color: 'error',
    decision: true,
    arrowLabel: 'No',
  },
  {
    id: 'deploy',
    icon: 'mdi-rocket-launch-outline',
    label: 'Deployment',
    agent: 'Status Agent',
    color: 'success',
  },
  {
    id: 'post-bug',
    icon: 'mdi-alert-circle-outline',
    label: 'Post-deploy bug?',
    agent: 'Status Agent',
    color: 'warning',
    decision: true,
    arrowLabel: 'No',
  },
  {
    id: 'learn',
    icon: 'mdi-brain',
    label: 'Learning & Skills',
    agent: 'Learning + Skill',
    color: 'primary',
  },
]
</script>
