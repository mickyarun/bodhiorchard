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


import type { ConnectionsSection, ConnectionsState } from '@/stores/settings'

/** Just the named sections of a connections object, for a partial PATCH. */
export function pickSections(source: ConnectionsState, sections: ConnectionsSection[]): Partial<ConnectionsState> {
  return Object.fromEntries(sections.map(key => [key, source[key]])) as Partial<ConnectionsState>
}

/** A deep copy of one section, to restore after a failed save or compare for changes. */
export function snapshotSection<K extends ConnectionsSection>(source: ConnectionsState, key: K): ConnectionsState[K] {
  return JSON.parse(JSON.stringify(source[key])) as ConnectionsState[K]
}

/** Whether a value differs from its snapshot, compared as plain data. */
export function differsFrom(value: unknown, snapshot: unknown): boolean {
  return JSON.stringify(value) !== JSON.stringify(snapshot)
}
