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

// Canonical list of public landing routes. Dependency-free (no Vue/router
// imports) so it can be consumed by BOTH the router/nav AND vite.landing.config
// (esbuild) when generating sitemap.xml — keeping the two from drifting.

export interface LandingRoute {
  path: string
  /** Vue Router route name. */
  name: string
  /** Nav / footer label. */
  label: string
  /** sitemap.xml priority (0.0–1.0). */
  priority: number
}

export const LANDING_ROUTES: LandingRoute[] = [
  { path: '/', name: 'home', label: 'Home', priority: 1.0 },
  { path: '/methodology', name: 'methodology', label: 'Methodology', priority: 0.8 },
  { path: '/agents', name: 'agents', label: 'Agents', priority: 0.8 },
  { path: '/platform', name: 'platform', label: 'Platform', priority: 0.8 },
  { path: '/vs-agile', name: 'vs-agile', label: 'vs Agile', priority: 0.8 },
  { path: '/why-bodhiorchard', name: 'why', label: 'Why', priority: 0.7 },
]

export const LANDING_PATHS: string[] = LANDING_ROUTES.map((r) => r.path)
