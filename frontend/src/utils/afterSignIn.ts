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
 * Where someone goes once they're signed in, after login or after changing a
 * temporary password: the garden avatar picker first if they're an engineer
 * without one, then the page they were going to, else their home.
 */
import type { RouteLocationRaw } from 'vue-router'
import type { User } from '@/types'
import { takeReturnTo } from '@/utils/returnTo'
import { canOpenWorkspace, homeRouteFor } from '@/utils/workspace'

type SignedIn = Pick<User, 'permissions' | 'character_model'> | null | undefined

export function afterSignIn(user: SignedIn): RouteLocationRaw {
  const permissions = user?.permissions
  if (canOpenWorkspace(permissions, 'engineering') && !user?.character_model) {
    // The avatar only matters in the engineering workspace; the page they
    // were going to stays remembered for after it (see CharacterSelectView).
    return { name: 'character-select' }
  }
  // No profile (it didn't load): let the router guard retry it rather than
  // guessing a workspace from an empty permission list.
  return takeReturnTo() ?? (permissions ? homeRouteFor(permissions) : '/')
}
