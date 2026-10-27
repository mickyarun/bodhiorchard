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

import type { SetupRepoSource } from '@/types/setup'

/**
 * Whether the setup wizard must read a newly added repo's branches by path.
 *
 * Only a ``local-path`` entry ever needs it, and only when the caller has
 * not resolved its develop branch yet (``undefined`` = not looked up,
 * ``null`` = looked up and none found). Every other source arrives with
 * its branches: a clone is already a tracked repo whose clone response
 * carries main and develop. The path lookup is also confined to the
 * picker roots, and in Full Docker the clone root (``/data/repos``) sits
 * outside them, so sending a cloned path there is refused.
 */
export function needsPathBranchLookup(
  source: SetupRepoSource,
  detectedDevelop: string | null | undefined,
): boolean {
  return source === 'local-path' && detectedDevelop === undefined
}
