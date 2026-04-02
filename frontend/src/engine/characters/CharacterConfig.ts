/**
 * CharacterConfig — Parse and serialize the character_model DB string.
 *
 * Encoding format: "kaykit:{characterId}:{shirtHex}:{pantsHex}:{skinHex}"
 * Example:         "kaykit:barbarian:FF6B35:2E4057:F4C28F"
 *
 * Legacy values (single letter like "b" or null) map to Kenney Blocky Characters.
 * This keeps backward compatibility with existing users.
 */

// ─── Default Colors ────────────────────────────

const DEFAULT_SHIRT_COLOR = 'C8553D'
const DEFAULT_PANTS_COLOR = '2E4057'
const DEFAULT_SKIN_COLOR  = 'F4C28F'
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

// ─── Types ─────────────────────────────────────

export interface CharacterConfig {
  pack: 'kaykit' | 'legacy'
  /** For kaykit: character id (e.g. "barbarian"). For legacy: variant letter (e.g. "b"). */
  characterId: string
  /** Shirt color as 6-char hex (no #). */
  shirtColor: string
  /** Pants color as 6-char hex (no #). */
  pantsColor: string
  /** Skin tone color as 6-char hex (no #). */
  skinColor: string
}

// ─── Parse ─────────────────────────────────────

/**
 * Parse the character_model DB string into a typed config.
 *
 * Handles three cases:
 *   null / empty         → legacy pack with hash-based variant (caller handles)
 *   single letter "b"    → legacy Kenney Blocky Character
 *   "kaykit:id:hex:hex:hex" → KayKit character with colors
 */
export function parseCharacterModel(raw: string | null): CharacterConfig {
  if (!raw || raw.length === 0) {
    return {
      pack: 'legacy',
      characterId: '',
      shirtColor: DEFAULT_SHIRT_COLOR,
      pantsColor: DEFAULT_PANTS_COLOR,
      skinColor: DEFAULT_SKIN_COLOR,
    }
  }

  // Legacy: single character variant letter (a-r)
  if (raw.length === 1) {
    return {
      pack: 'legacy',
      characterId: raw,
      shirtColor: DEFAULT_SHIRT_COLOR,
      pantsColor: DEFAULT_PANTS_COLOR,
      skinColor: DEFAULT_SKIN_COLOR,
    }
  }

  // KayKit format: "kaykit:characterId:shirtHex:pantsHex:skinHex"
  if (raw.startsWith('kaykit:')) {
    const parts = raw.split(':')
    return {
      pack: 'kaykit',
      characterId: parts[1] || DEFAULT_CHARACTER_ID,
      shirtColor: sanitizeHex(parts[2] || '', DEFAULT_SHIRT_COLOR),
      pantsColor: sanitizeHex(parts[3] || '', DEFAULT_PANTS_COLOR),
      skinColor: sanitizeHex(parts[4] || '', DEFAULT_SKIN_COLOR),
    }
  }

  // Unknown format → treat as legacy
  return {
    pack: 'legacy',
    characterId: raw,
    shirtColor: DEFAULT_SHIRT_COLOR,
    pantsColor: DEFAULT_PANTS_COLOR,
    skinColor: DEFAULT_SKIN_COLOR,
  }
}

// ─── Serialize ─────────────────────────────────

/**
 * Serialize a character config back to the DB string format.
 * Only KayKit configs produce the full encoding; legacy returns the variant letter.
 */
export function serializeCharacterConfig(config: CharacterConfig): string {
  if (config.pack === 'legacy') {
    return config.characterId
  }

  const shirt = sanitizeHex(config.shirtColor, DEFAULT_SHIRT_COLOR)
  const pants = sanitizeHex(config.pantsColor, DEFAULT_PANTS_COLOR)
  const skin = sanitizeHex(config.skinColor, DEFAULT_SKIN_COLOR)

  const id = config.characterId.replace(/:/g, '')
  return `kaykit:${id}:${shirt}:${pants}:${skin}`
}

// ─── Helpers ───────────────────────────────────

export function isKayKitConfig(config: CharacterConfig): boolean {
  return config.pack === 'kaykit'
}

export { DEFAULT_SHIRT_COLOR, DEFAULT_PANTS_COLOR, DEFAULT_SKIN_COLOR }
