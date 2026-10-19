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
 * A copy of `source` that only catches up once it has stopped changing for
 * `delayMs`, e.g. so a search box doesn't send a request per keystroke.
 */
import { getCurrentScope, onScopeDispose, type Ref, ref, watch } from 'vue'

export const SEARCH_DELAY_MS = 250

export function useDebounced<T>(source: Ref<T>, delayMs = SEARCH_DELAY_MS): Ref<T> {
  const settled = ref(source.value) as Ref<T>
  let timer: ReturnType<typeof setTimeout> | undefined

  watch(source, value => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      settled.value = value
    }, delayMs)
  })

  if (getCurrentScope()) onScopeDispose(() => clearTimeout(timer))
  return settled
}
