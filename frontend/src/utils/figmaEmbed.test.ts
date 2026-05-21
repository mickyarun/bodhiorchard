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

import { describe, it, expect } from 'vitest'

import { toEmbedUrl } from './figmaEmbed'

describe('toEmbedUrl', () => {
  // Each accepted share-URL shape should map to the matching embed-host
  // path. ``embed-host=bodhiorchard`` is non-negotiable — Figma rejects
  // the embed handshake without one.

  it('maps /design/ URLs without node-id', () => {
    const url = 'https://www.figma.com/design/H6JqUCUEsvDguwpI7JEujN/BD6-File'
    expect(toEmbedUrl(url)).toBe(
      'https://embed.figma.com/design/H6JqUCUEsvDguwpI7JEujN?embed-host=bodhiorchard',
    )
  })

  it('maps /file/ URLs without node-id', () => {
    const url = 'https://www.figma.com/file/ABC123/Legacy-File'
    expect(toEmbedUrl(url)).toBe(
      'https://embed.figma.com/file/ABC123?embed-host=bodhiorchard',
    )
  })

  it('maps /proto/ URLs without node-id', () => {
    const url = 'https://www.figma.com/proto/XYZ789/Prototype-Flow'
    expect(toEmbedUrl(url)).toBe(
      'https://embed.figma.com/proto/XYZ789?embed-host=bodhiorchard',
    )
  })

  it('forwards node-id from a /design/ URL', () => {
    const url = 'https://www.figma.com/design/H6JqUCUEsvDguwpI7JEujN/BD6?node-id=29471-2639'
    // URL-encoded "node-id" becomes "node-id" (no encoding needed) but
    // the value's hyphen is preserved verbatim — Figma's embed accepts
    // the dash form.
    expect(toEmbedUrl(url)).toBe(
      'https://embed.figma.com/design/H6JqUCUEsvDguwpI7JEujN?embed-host=bodhiorchard&node-id=29471-2639',
    )
  })

  it('forwards node-id from a /proto/ URL with extra query params', () => {
    // Real prototype URLs carry several params (starting-point-node-id,
    // viewport, etc.). We deliberately forward ONLY node-id; the rest
    // are noise that can break Figma's embed handshake.
    const url = 'https://www.figma.com/proto/XYZ789/Flow?node-id=1-2&starting-point-node-id=1-2&scaling=scale-down&t=abc'
    expect(toEmbedUrl(url)).toBe(
      'https://embed.figma.com/proto/XYZ789?embed-host=bodhiorchard&node-id=1-2',
    )
  })

  it('accepts URLs without the www. prefix', () => {
    // Figma URLs from Slack share links sometimes lack the www. prefix.
    const url = 'https://figma.com/design/ABC123/X'
    expect(toEmbedUrl(url)).toBe(
      'https://embed.figma.com/design/ABC123?embed-host=bodhiorchard',
    )
  })

  // Malformed input contract — return null so the Design tab can show
  // an inline parse-error callout instead of feeding a broken URL to
  // the iframe.

  it('returns null for a non-Figma URL', () => {
    expect(toEmbedUrl('https://example.com/foo')).toBeNull()
  })

  it('returns null for a Figma URL with an unsupported path', () => {
    // ``/community/`` is a real Figma path but it's not an embeddable
    // file/design/proto link.
    expect(toEmbedUrl('https://www.figma.com/community/file/ABC123/x')).toBeNull()
  })

  it('returns null for an empty string', () => {
    expect(toEmbedUrl('')).toBeNull()
  })

  it('returns null for whitespace-only input', () => {
    expect(toEmbedUrl('   ')).toBeNull()
  })

  it('returns null for null / undefined', () => {
    expect(toEmbedUrl(null)).toBeNull()
    expect(toEmbedUrl(undefined)).toBeNull()
  })

  it('returns null for a URL that merely contains the figma pattern as a substring', () => {
    // Defence against a chat-log style input — the anchor ``^`` prevents
    // matching mid-string.
    expect(toEmbedUrl('see https://www.figma.com/design/ABC/X for the spec')).toBeNull()
  })
})
