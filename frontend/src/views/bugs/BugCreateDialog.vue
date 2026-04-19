<template>
  <v-dialog :model-value="modelValue" max-width="520" @update:model-value="$emit('update:modelValue', $event)">
    <v-card color="surface" class="pa-6">
      <div class="text-h6 font-weight-bold mb-4">Report a Bug</div>

      <v-text-field
        v-model="title"
        label="Title *"
        variant="outlined"
        density="compact"
        class="mb-3"
        :rules="[v => !!v?.trim() || 'Title is required']"
      />

      <v-textarea
        v-model="description"
        label="Description"
        variant="outlined"
        density="compact"
        rows="3"
        class="mb-3"
        placeholder="Steps to reproduce, expected vs actual behavior..."
      />

      <div class="d-flex ga-3 mb-3">
        <v-select
          v-model="severity"
          :items="severityOptions"
          label="Severity"
          variant="outlined"
          density="compact"
          style="flex: 1"
        />
        <v-text-field
          v-model="module"
          label="Module / Area"
          variant="outlined"
          density="compact"
          style="flex: 1"
          placeholder="e.g. payments, auth"
        />
      </div>

      <v-text-field
        v-if="!budId"
        v-model="linkedBudSearch"
        label="Link to BUD (optional)"
        variant="outlined"
        density="compact"
        placeholder="Leave empty for AI auto-linking"
        hint="AI will auto-detect the closest BUD if left empty"
        persistent-hint
      />

      <v-card-actions class="pa-0 mt-4">
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn
          color="error"
          variant="flat"
          :disabled="!title?.trim()"
          :loading="saving"
          @click="submit"
        >
          Report Bug
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useBugsStore } from '@/stores/bugs'
import type { BugRead } from '@/types'

const props = defineProps<{
  modelValue: boolean
  budId?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', bug: BugRead): void
}>()

const bugsStore = useBugsStore()

const title = ref('')
const description = ref('')
const severity = ref('medium')
const module = ref('')
const linkedBudSearch = ref('')
const saving = ref(false)

const severityOptions = [
  { title: 'Low', value: 'low' },
  { title: 'Medium', value: 'medium' },
  { title: 'High', value: 'high' },
  { title: 'Critical', value: 'critical' },
]

async function submit(): Promise<void> {
  if (!title.value.trim()) return
  saving.value = true
  const bug = await bugsStore.createBug({
    title: title.value.trim(),
    description: description.value.trim() || undefined,
    severity: severity.value,
    module: module.value.trim() || undefined,
    budId: props.budId || undefined,
  })
  saving.value = false
  if (bug) {
    title.value = ''
    description.value = ''
    severity.value = 'medium'
    module.value = ''
    linkedBudSearch.value = ''
    emit('update:modelValue', false)
    emit('created', bug)
  }
}
</script>
