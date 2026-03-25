<template>
  <div class="task-board">
    <h1>Task Board</h1>
    <div class="board-columns">
      <div v-for="col in columns" :key="col.status" class="column">
        <h2>{{ col.label }} ({{ col.tasks.length }})</h2>
        <div
          v-for="task in col.tasks"
          :key="task.id"
          class="task-card"
          @click="openTask(task.id)"
        >
          <span class="priority" :class="task.priority">{{ task.priority }}</span>
          <h3>{{ task.title }}</h3>
          <p v-if="task.assignee">{{ task.assignee }}</p>
        </div>
      </div>
    </div>

    <button class="fab" @click="showCreateDialog = true">+ New Task</button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/services/api'

interface Task {
  id: number
  title: string
  status: string
  priority: string
  assignee?: string
}

const router = useRouter()
const tasks = ref<Task[]>([])
const showCreateDialog = ref(false)

const columns = computed(() => [
  { status: 'todo', label: 'To Do', tasks: tasks.value.filter(t => t.status === 'todo') },
  { status: 'in_progress', label: 'In Progress', tasks: tasks.value.filter(t => t.status === 'in_progress') },
  { status: 'in_review', label: 'In Review', tasks: tasks.value.filter(t => t.status === 'in_review') },
  { status: 'done', label: 'Done', tasks: tasks.value.filter(t => t.status === 'done') },
])

onMounted(async () => {
  const { data } = await api.get('/tasks')
  tasks.value = data
})

function openTask(id: number) {
  router.push(`/tasks/${id}`)
}
</script>
