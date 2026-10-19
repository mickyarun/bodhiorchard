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
 * Ask before throwing away unsaved edits: on leaving the route, on a query
 * change that would unmount the form (any of `queryKeys` changing), and on
 * closing the tab. Render a confirm dialog on `asking` and call `answer`.
 */
import { onBeforeUnmount, onMounted, type Ref, ref } from 'vue'
import {
  onBeforeRouteLeave,
  onBeforeRouteUpdate,
  type RouteLocationNormalized,
} from 'vue-router'

export function useUnsavedGuard(dirty: Ref<boolean>, queryKeys: readonly string[]) {
  const asking = ref(false)
  let resolve: ((leave: boolean) => void) | null = null

  function ask(): Promise<boolean> {
    resolve?.(false)
    asking.value = true
    return new Promise(done => {
      resolve = done
    })
  }

  function answer(leave: boolean): void {
    asking.value = false
    resolve?.(leave)
    resolve = null
  }

  function unmountsForm(to: RouteLocationNormalized, from: RouteLocationNormalized): boolean {
    return queryKeys.some(key => to.query[key] !== from.query[key])
  }

  onBeforeRouteLeave(() => (dirty.value ? ask() : true))
  onBeforeRouteUpdate((to, from) => (dirty.value && unmountsForm(to, from) ? ask() : true))

  function onBeforeUnload(event: BeforeUnloadEvent): void {
    if (!dirty.value) return
    event.preventDefault()
    // Older Safari and Firefox only prompt when returnValue is set.
    event.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', onBeforeUnload)
    answer(false)
  })

  return { asking, answer }
}
