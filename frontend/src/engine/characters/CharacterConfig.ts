/**
 * CharacterConfig — Parse and serialize the character_model DB string.
 *
 * Encoding format: "kaykit:{characterId}:{shirtHex}:{pantsHex}:{skinHex}:{rightHand}:{leftHand}"
 * Example:         "kaykit:barbarian:FF6B35:2E4057:F4C28F:sword:shield"
 *
 * Accessories are optional — empty string or missing segments mean no accessory.
 * Legacy values (single letter like "b" or null) map to Kenney Blocky Characters.
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

/** Sanitize an accessory ID — only lowercase letters and underscores allowed. */
function sanitizeAccessoryId(s: string): string {
  return s.replace(/[^a-z_]/g, '')
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
  /** Right hand accessory id (empty = none). */
  rightHand: string
  /** Left hand accessory id (empty = none). */
  leftHand: string
}

// ─── Parse ─────────────────────────────────────

function makeLegacyConfig(characterId: string): CharacterConfig {
  return {
    pack: 'legacy',
    characterId,
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
 * Handles:
 *   null / empty                          → legacy (hash-based variant)
 *   single letter "b"                     → legacy Kenney Blocky Character
 *   "kaykit:id:hex:hex:hex"               → KayKit character (no accessories)
 *   "kaykit:id:hex:hex:hex:right:left"    → KayKit character with accessories
 */
export function parseCharacterModel(raw: string | null): CharacterConfig {
  if (!raw || raw.length === 0) return makeLegacyConfig('')
  if (raw.length === 1) return makeLegacyConfig(raw)

  if (raw.startsWith('kaykit:')) {
    const parts = raw.split(':')
    return {
      pack: 'kaykit',
      characterId: parts[1] || DEFAULT_CHARACTER_ID,
      shirtColor: sanitizeHex(parts[2] || '', DEFAULT_SHIRT_COLOR),
      pantsColor: sanitizeHex(parts[3] || '', DEFAULT_PANTS_COLOR),
      skinColor: sanitizeHex(parts[4] || '', DEFAULT_SKIN_COLOR),
      rightHand: sanitizeAccessoryId(parts[5] || ''),
      leftHand: sanitizeAccessoryId(parts[6] || ''),
    }
  }

  return makeLegacyConfig(raw)
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

  const id = config.characterId.replace(/:/g, '')
  const shirt = sanitizeHex(config.shirtColor, DEFAULT_SHIRT_COLOR)
  const pants = sanitizeHex(config.pantsColor, DEFAULT_PANTS_COLOR)
  const skin = sanitizeHex(config.skinColor, DEFAULT_SKIN_COLOR)
  const right = sanitizeAccessoryId(config.rightHand)
  const left = sanitizeAccessoryId(config.leftHand)

  return `kaykit:${id}:${shirt}:${pants}:${skin}:${right}:${left}`
}

// ─── Helpers ───────────────────────────────────

export function isKayKitConfig(config: CharacterConfig): boolean {
  return config.pack === 'kaykit'
}

export { DEFAULT_SHIRT_COLOR, DEFAULT_PANTS_COLOR, DEFAULT_SKIN_COLOR }
