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
 * CharacterConfig — Parse and serialize the character_model DB string.
 *
 * Encoding format: "kaykit:{characterId}:{shirtHex}:{pantsHex}:{skinHex}:{rightHand}:{leftHand}"
 * Example:         "kaykit:barbarian:FF6B35:2E4057:F4C28F:sword:shield"
 *
 * Accessories are optional — empty string or missing segments mean no accessory.
 * The legacy single-letter Kenney Blocky encoding was dropped when the garden
 * unified on KayKit; callers that pass `null`, `""`, or a legacy single-letter
 * string now get a default KayKit config instead.
 */

// ─── Default Colors ────────────────────────────

const DEFAULT_SHIRT_COLOR = 'C8553D'
const DEFAULT_PANTS_COLOR = '2E4057'
const DEFAULT_SKIN_COLOR  = 'F4C28F'

/**
 * The fallback KayKit character for users whose `character_model` hasn't
 * been set (new signups, imported accounts, test fixtures). `barbarian`
 * is unlocked from level 1 so nobody ends up with a locked preset.
 */
const DEFAULT_CHARACTER_ID = 'barbarian'

// ─── Hex Validation ────────────────────────────

const HEX_RE = /^[0-9A-Fa-f]{6}$/

function isValidHex(s: string): boolean {
  return HEX_RE.test(s)
}

function sanitizeHex(s: string, fallback: string): string {
  const clean = s.replace(/[^0-9A-Fa-f]/g, '').toUpperCase()
  return clean.length === 6 && isValidHex(clean) ? clean : fallback
}

/** Sanitize an accessory ID — only lowercase letters and underscores allowed. */
function sanitizeAccessoryId(s: string): string {
  return s.replace(/[^a-z_]/g, '')
}

// ─── Types ─────────────────────────────────────

export interface CharacterConfig {
  /** KayKit character id (e.g. "barbarian"). Always set — defaults apply. */
  characterId: string
  /** Shirt color as 6-char hex (no #). */
  shirtColor: string
  /** Pants color as 6-char hex (no #). */
  pantsColor: string
  /** Skin tone color as 6-char hex (no #). */
  skinColor: string
  /** Right hand accessory id (empty = none). */
  rightHand: string
  /** Left hand accessory id (empty = none). */
  leftHand: string
}

// ─── Parse ─────────────────────────────────────

function defaultConfig(): CharacterConfig {
  return {
    characterId: DEFAULT_CHARACTER_ID,
    shirtColor: DEFAULT_SHIRT_COLOR,
    pantsColor: DEFAULT_PANTS_COLOR,
    skinColor: DEFAULT_SKIN_COLOR,
    rightHand: '',
    leftHand: '',
  }
}

/**
 * Parse the character_model DB string into a typed config.
 *
 * Anything other than a well-formed "kaykit:id:hex:hex:hex[:right:left]"
 * string — null, empty, old single-letter Kenney ids, corrupted data —
 * falls through to `defaultConfig()`, guaranteeing every caller receives
 * a spawnable KayKit config.
 */
export function parseCharacterModel(raw: string | null): CharacterConfig {
  if (!raw || !raw.startsWith('kaykit:')) return defaultConfig()

  const parts = raw.split(':')
  const characterId = parts[1]?.trim() || DEFAULT_CHARACTER_ID
  return {
    characterId,
    shirtColor: sanitizeHex(parts[2] || '', DEFAULT_SHIRT_COLOR),
    pantsColor: sanitizeHex(parts[3] || '', DEFAULT_PANTS_COLOR),
    skinColor: sanitizeHex(parts[4] || '', DEFAULT_SKIN_COLOR),
    rightHand: sanitizeAccessoryId(parts[5] || ''),
    leftHand: sanitizeAccessoryId(parts[6] || ''),
  }
}

// ─── Serialize ─────────────────────────────────

/** Serialize a config back to the DB string format. */
export function serializeCharacterConfig(config: CharacterConfig): string {
  const id = (config.characterId || DEFAULT_CHARACTER_ID).replace(/:/g, '')
  const shirt = sanitizeHex(config.shirtColor, DEFAULT_SHIRT_COLOR)
  const pants = sanitizeHex(config.pantsColor, DEFAULT_PANTS_COLOR)
  const skin = sanitizeHex(config.skinColor, DEFAULT_SKIN_COLOR)
  const right = sanitizeAccessoryId(config.rightHand)
  const left = sanitizeAccessoryId(config.leftHand)
  return `kaykit:${id}:${shirt}:${pants}:${skin}:${right}:${left}`
}

export { DEFAULT_SHIRT_COLOR, DEFAULT_PANTS_COLOR, DEFAULT_SKIN_COLOR, DEFAULT_CHARACTER_ID }
