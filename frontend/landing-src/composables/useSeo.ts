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

// Per-route head/SEO for the landing site. Wraps unhead's useHead (bundled by
// vite-ssg) to emit a consistent title + description + canonical + Open Graph +
// Twitter card, plus optional JSON-LD, from one call per page. Landing-only —
// the main app does not ship unhead, so this lives under landing-src/.

import { useHead } from '@unhead/vue'
import { SITE_ORIGIN } from '../routes-manifest'

const BASE = SITE_ORIGIN
const DEFAULT_IMAGE = `${BASE}/landing/bodhiorchard-logo.png`

export interface SeoMeta {
  /** Document title (also og:title / twitter:title). */
  title: string
  /** Meta description (also og:description / twitter:description). */
  description: string
  /** Route path, e.g. '/agents'. Used to build the absolute canonical URL. */
  path: string
  /** Absolute OG/Twitter image URL. Defaults to the wordmark. */
  image?: string
  /** og:type. Defaults to 'website'. */
  type?: string
  /** One JSON-LD object or several, emitted as <script type="application/ld+json">. */
  jsonLd?: Record<string, unknown> | Record<string, unknown>[]
  /** Mark the page noindex and omit the canonical (e.g. the client-side 404). */
  noindex?: boolean
}

export function useSeo(meta: SeoMeta): void {
  const url = `${BASE}${meta.path}`
  const image = meta.image ?? DEFAULT_IMAGE
  const blobs = meta.jsonLd ? (Array.isArray(meta.jsonLd) ? meta.jsonLd : [meta.jsonLd]) : []

  useHead({
    title: meta.title,
    // A noindex page (the SPA 404 fallback) gets no self-referential canonical
    // to a URL that isn't pre-rendered or in the sitemap.
    link: meta.noindex ? [] : [{ rel: 'canonical', href: url }],
    meta: [
      { name: 'description', content: meta.description },
      ...(meta.noindex ? [{ name: 'robots', content: 'noindex' }] : []),
      { property: 'og:type', content: meta.type ?? 'website' },
      { property: 'og:url', content: url },
      { property: 'og:title', content: meta.title },
      { property: 'og:description', content: meta.description },
      { property: 'og:image', content: image },
      { property: 'og:site_name', content: 'Bodhiorchard' },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:title', content: meta.title },
      { name: 'twitter:description', content: meta.description },
      { name: 'twitter:image', content: image },
    ],
    script: blobs.map((blob) => ({
      type: 'application/ld+json',
      children: JSON.stringify(blob),
    })),
  })
}
