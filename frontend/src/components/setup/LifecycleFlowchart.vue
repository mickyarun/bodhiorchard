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
  <div class="cycle-wrapper">
    <!-- Circular flow (always centered, no shift) -->
    <div class="cycle-flow">
      <!-- SVG layer -->
      <svg class="cycle-flow__svg" viewBox="0 0 500 500">
        <defs>
          <radialGradient id="dotGlow">
            <stop offset="0%" stop-color="rgb(99,102,241)" stop-opacity="0.8" />
            <stop offset="100%" stop-color="rgb(99,102,241)" stop-opacity="0" />
          </radialGradient>
          <marker id="arrowRed" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(239,68,68,0.7)" />
          </marker>
        </defs>

        <!-- Circle track -->
        <circle cx="250" cy="250" r="180"
          fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="2" />

        <!-- Dashed ring -->
        <circle cx="250" cy="250" r="180"
          fill="none" stroke="rgba(99,102,241,0.12)" stroke-width="2"
          stroke-dasharray="8 8" class="cycle-flow__dash" />

        <!-- Bug → Feature connecting line -->
        <line
          :x1="bugSvgX" :y1="bugSvgY"
          :x2="featureSvgX" :y2="featureSvgY"
          stroke="rgba(239,68,68,0.5)"
          stroke-width="2"
          stroke-dasharray="6 4"
          marker-end="url(#arrowRed)"
          class="cycle-flow__bug-line"
        />

        <!-- Dot glow -->
        <circle :cx="dotX" :cy="dotY" r="22"
          fill="url(#dotGlow)" class="cycle-flow__glow" />

        <!-- Dot -->
        <circle :cx="dotX" :cy="dotY" r="5"
          fill="rgb(99,102,241)" class="cycle-flow__dot" />
      </svg>

      <!-- Center: phase description -->
      <div class="cycle-flow__center">
        <transition name="fade" mode="out-in">
          <div v-if="activePhase === -1" key="bug" class="text-center">
            <v-icon icon="mdi-bug-outline" size="28" color="error" />
            <div class="text-caption font-weight-bold mt-1">External Bug</div>
            <div class="cycle-center__desc">
              Reopens Feature and restarts the flow from triage
            </div>
          </div>
          <div v-else :key="activePhase" class="text-center">
            <v-icon :icon="nodes[activePhase].icon" size="28"
              :color="nodes[activePhase].color" />
            <div class="text-caption font-weight-bold mt-1">{{ nodes[activePhase].label }}</div>
            <div class="cycle-center__desc">{{ nodes[activePhase].centerDesc }}</div>
          </div>
        </transition>
      </div>

      <!-- Phase nodes on the circle -->
      <div
        v-for="(node, i) in nodes"
        :key="node.id"
        class="cycle-node"
        :class="{ 'cycle-node--active': activePhase === i }"
        :style="nodePosition(i)"
        @mouseenter="setActive(i)"
        @mouseleave="scheduleResume"
      >
        <div class="cycle-node__icon"
          :style="{ '--node-color': `var(--v-theme-${node.color})` }">
          <v-icon :icon="node.icon" size="18" />
        </div>
        <div class="cycle-node__label">{{ node.label }}</div>
        <div class="cycle-node__agent">{{ node.agent }}</div>
      </div>

      <!-- Bug node (far outside the circle) -->
      <div
        class="cycle-node cycle-node--bug"
        :class="{ 'cycle-node--active': activePhase === -1 }"
        :style="bugPosition"
        @mouseenter="showBugInfo"
        @mouseleave="scheduleResume"
      >
        <div class="cycle-node__icon" style="--node-color: var(--v-theme-error);">
          <v-icon icon="mdi-bug-outline" size="18" />
        </div>
        <div class="cycle-node__label">External Bug</div>
        <div class="cycle-node__agent">Reopens Feature</div>
      </div>
    </div>

    <!-- Agent panel: overlays from right on hover -->
    <div class="cycle-info" :class="{ 'cycle-info--visible': panelVisible }">
      <transition name="slide-info" mode="out-in">
        <!-- Bug agents -->
        <div v-if="activePhase === -1" key="bug" class="cycle-info__card">
          <div v-for="(agent, idx) in bugAgents" :key="agent.name">
            <v-divider v-if="idx > 0" class="my-3" style="opacity: 0.08;" />
            <div class="cycle-info__header">
              <div class="cycle-info__icon"
                :style="{ background: `rgba(var(--v-theme-${agent.color}), 0.15)` }">
                <v-icon :icon="agent.icon" size="22" :color="agent.color" />
              </div>
              <div>
                <div class="text-body-2 font-weight-bold">{{ agent.name }}</div>
                <v-chip :prepend-icon="agent.triggerIcon" size="x-small" variant="tonal"
                  :color="agent.color" class="mt-1">
                  {{ agent.triggerType }}
                </v-chip>
              </div>
            </div>
            <div class="text-caption text-medium-emphasis mt-2" style="line-height: 1.5;">
              {{ agent.tagline }}
            </div>
            <div class="d-flex flex-wrap ga-1 mt-2">
              <v-chip v-for="cap in agent.capabilities" :key="cap"
                size="x-small" variant="outlined" :color="agent.color"
                class="agent-cap-chip">
                {{ cap }}
              </v-chip>
            </div>
          </div>
        </div>

        <!-- Phase agents -->
        <div v-else :key="activePhase" class="cycle-info__card">
          <div v-for="(agent, idx) in activeAgents" :key="agent.name">
            <v-divider v-if="idx > 0" class="my-3" style="opacity: 0.08;" />
            <div class="cycle-info__header">
              <div class="cycle-info__icon"
                :style="{ background: `rgba(var(--v-theme-${agent.color}), 0.15)` }">
                <v-icon :icon="agent.icon" size="22" :color="agent.color" />
              </div>
              <div>
                <div class="text-body-2 font-weight-bold">{{ agent.name }}</div>
                <v-chip :prepend-icon="agent.triggerIcon" size="x-small" variant="tonal"
                  :color="agent.color" class="mt-1">
                  {{ agent.triggerType }}
                </v-chip>
              </div>
            </div>
            <div class="text-caption text-medium-emphasis mt-2" style="line-height: 1.5;">
              {{ agent.tagline }}
            </div>
            <div class="d-flex flex-wrap ga-1 mt-2">
              <v-chip v-for="cap in agent.capabilities" :key="cap"
                size="x-small" variant="outlined" :color="agent.color"
                class="agent-cap-chip">
                {{ cap }}
              </v-chip>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { agents, type AgentInfo } from '@/data/agents'

interface PhaseNode {
  id: string
  icon: string
  label: string
  agent: string
  color: string
  centerDesc: string
  agentNames: string[]
}

const nodes: PhaseNode[] = [
  {
    id: 'intake', icon: 'mdi-chat-outline', label: 'Chat Intake',
    agent: 'Triage Agent', color: 'primary',
    centerDesc: 'Incoming requests analyzed, deduplicated, and prioritized automatically',
    agentNames: ['Triage Agent'],
  },
  {
    id: 'bud', icon: 'mdi-seed-outline', label: 'BUD Generation',
    agent: 'BUD Agent', color: 'secondary',
    centerDesc: 'Full spec generated by AI; PM reviews, refines, and advances to Design',
    agentNames: ['BUD Agent'],
  },
  {
    id: 'design', icon: 'mdi-palette-outline', label: 'Design',
    agent: 'Design Agent', color: 'primary',
    centerDesc: 'AI wireframes reviewed and edited by Designer before advancing',
    agentNames: ['Design Agent'],
  },
  {
    id: 'tech_arch', icon: 'mdi-file-tree-outline', label: 'Tech Architecture',
    agent: 'Tech Planner', color: 'deep-purple',
    centerDesc: 'AI-generated plan reviewed by Tech Lead; Smart Assignment Agent assigns developer',
    agentNames: ['Tech Plan Agent'],
  },
  {
    id: 'dev', icon: 'mdi-code-braces', label: 'Development',
    agent: 'AI + Human', color: 'info',
    centerDesc: 'AI implements from tech plan, human reviews the code',
    agentNames: ['Tech Plan Agent', 'Smart Assignment Agent', 'Standup Agent'],
  },
  {
    id: 'test', icon: 'mdi-test-tube', label: 'Test Generation',
    agent: 'Test Agent', color: 'warning',
    centerDesc: 'Automated tests and manual cases from acceptance criteria',
    agentNames: ['Test Plan Agent'],
  },
  {
    id: 'testing', icon: 'mdi-clipboard-check-outline', label: 'Testing',
    agent: 'QA + Test Agent', color: 'error',
    centerDesc: 'QA reviews automation plan, executes manual tests, signs off',
    agentNames: ['Test Plan Agent'],
  },
  {
    id: 'deploy', icon: 'mdi-rocket-launch-outline', label: 'UAT & Deploy',
    agent: 'Status Agent', color: 'success',
    centerDesc: 'Validates in UAT, deploys to production, notifies stakeholders',
    agentNames: ['Status Agent'],
  },
  {
    id: 'feature', icon: 'mdi-star-shooting-outline', label: 'Feature',
    agent: 'BUD \u2192 Feature', color: 'success',
    centerDesc: 'BUD graduates to a permanent Feature record in the registry',
    agentNames: ['Status Agent'],
  },
  {
    id: 'learn', icon: 'mdi-brain', label: 'Learning & Skills',
    agent: 'Learning + Skill', color: 'primary',
    centerDesc: 'Cycle time analysis, retrospectives, and skill profile updates',
    agentNames: ['Learning Agent', 'Skill Agent'],
  },
]

// Build a lookup map for agents by name
const agentMap = new Map<string, AgentInfo>(
  agents.map(a => [a.name, a])
)

function getAgentsByNames(names: string[]): AgentInfo[] {
  return names.map(n => agentMap.get(n)).filter((a): a is AgentInfo => !!a)
}

// Bug node maps to these agents
const bugAgents = getAgentsByNames(['Bug Linker Agent', 'Reassignment Agent'])

const NODE_COUNT = nodes.length
const RADIUS = 36
const SVG_RADIUS = 180
const SVG_CENTER = 250

const activePhase = ref(0)
const panelVisible = ref(false)
let autoInterval: ReturnType<typeof setInterval> | null = null
let resumeTimer: ReturnType<typeof setTimeout> | null = null

const activeAgents = computed(() =>
  getAgentsByNames(nodes[activePhase.value]?.agentNames || nodes[0].agentNames)
)

function getAngle(index: number): number {
  return (index * 2 * Math.PI) / NODE_COUNT - Math.PI / 2
}

function nodePosition(index: number): Record<string, string> {
  const angle = getAngle(index)
  return {
    left: `${50 + RADIUS * Math.cos(angle)}%`,
    top: `${50 + RADIUS * Math.sin(angle)}%`,
  }
}

// Feature node (index 7)
const featureAngle = getAngle(7)
const featureSvgX = SVG_CENTER + SVG_RADIUS * Math.cos(featureAngle)
const featureSvgY = SVG_CENTER + SVG_RADIUS * Math.sin(featureAngle)

// Bug node: well outside the circle, offset from Feature
const featurePctX = 50 + RADIUS * Math.cos(featureAngle)
const featurePctY = 50 + RADIUS * Math.sin(featureAngle)
const bugPctX = featurePctX - 18
const bugPctY = featurePctY + 8
const bugPosition = { left: `${bugPctX}%`, top: `${bugPctY}%` }
const bugSvgX = (bugPctX / 100) * 500
const bugSvgY = (bugPctY / 100) * 500

// Dot position
const dotX = computed(() => {
  if (activePhase.value === -1) return bugSvgX
  return SVG_CENTER + SVG_RADIUS * Math.cos(getAngle(activePhase.value))
})
const dotY = computed(() => {
  if (activePhase.value === -1) return bugSvgY
  return SVG_CENTER + SVG_RADIUS * Math.sin(getAngle(activePhase.value))
})

function cancelResume(): void {
  if (resumeTimer) {
    clearTimeout(resumeTimer)
    resumeTimer = null
  }
}

function setActive(index: number): void {
  cancelResume()
  panelVisible.value = true
  activePhase.value = index
}

function showBugInfo(): void {
  cancelResume()
  panelVisible.value = true
  activePhase.value = -1
}

function scheduleResume(): void {
  cancelResume()
  resumeTimer = setTimeout(() => {
    panelVisible.value = false
  }, 250)
}

onMounted(() => {
  autoInterval = setInterval(() => {
    if (!panelVisible.value) {
      activePhase.value = (activePhase.value + 1) % NODE_COUNT
    }
  }, 2500)
})

onUnmounted(() => {
  if (autoInterval) clearInterval(autoInterval)
  cancelResume()
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-info-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-info-leave-active {
  transition: all 0.15s ease;
}
.slide-info-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.slide-info-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.cycle-center__desc {
  font-size: 0.6rem;
  color: rgba(255, 255, 255, 0.5);
  line-height: 1.3;
  margin-top: 4px;
}
</style>
