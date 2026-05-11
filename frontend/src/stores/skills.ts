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

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { SkillProfile } from '@/types'

export const useSkillsStore = defineStore('skills', () => {
  const profiles = ref<SkillProfile[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchProfiles(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/skills/profiles')
      profiles.value = data
    } catch {
      error.value = 'Failed to load skill profiles.'
    } finally {
      loading.value = false
    }
  }

  return {
    profiles,
    loading,
    error,
    fetchProfiles,
  }
})
