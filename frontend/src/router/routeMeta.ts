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

import type { Workspace } from '@/utils/workspace'

// Typed route meta for the guards in router/guards.ts.
declare module 'vue-router' {
  interface RouteMeta {
    /** Permission(s) required; an array means any one of them is enough. */
    permission?: string | string[]
    /** Workspace the route belongs to; users without it are sent home. */
    workspace?: Workspace
  }
}

export {}
