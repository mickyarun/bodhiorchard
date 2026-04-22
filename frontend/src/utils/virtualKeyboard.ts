// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * virtualKeyboard — dispatch synthetic KeyboardEvents for touch controls.
 *
 * The in-game controllers (TakeoverController, RaceInput, emote / seat /
 * mount handlers in GardenEngine) all read keyboard state from
 * `pc.Keyboard` or `window` keydown listeners. Rather than adding touch
 * branches to every controller, touch widgets dispatch real
 * KeyboardEvents at the window and the existing input paths pick them
 * up unchanged.
 *
 * `pc.Keyboard` internally reads `event.keyCode` — deprecated in the DOM
 * spec but still honoured when set via the KeyboardEventInit dict. That
 * is why every entry below carries `keyCode`.
 */

interface KeyDef {
  code: string
  key: string
  keyCode: number
}

export type VirtualKeyName =
  | 'KeyW' | 'KeyA' | 'KeyS' | 'KeyD'
  | 'KeyE' | 'KeyV'
  | 'Space' | 'ShiftLeft' | 'Escape'
  | 'Digit1' | 'Digit2' | 'Digit3' | 'Digit4'

const KEY_MAP: Record<VirtualKeyName, KeyDef> = {
  KeyW:      { code: 'KeyW',      key: 'w',      keyCode: 87 },
  KeyA:      { code: 'KeyA',      key: 'a',      keyCode: 65 },
  KeyS:      { code: 'KeyS',      key: 's',      keyCode: 83 },
  KeyD:      { code: 'KeyD',      key: 'd',      keyCode: 68 },
  KeyE:      { code: 'KeyE',      key: 'e',      keyCode: 69 },
  KeyV:      { code: 'KeyV',      key: 'v',      keyCode: 86 },
  Space:     { code: 'Space',     key: ' ',      keyCode: 32 },
  ShiftLeft: { code: 'ShiftLeft', key: 'Shift',  keyCode: 16 },
  Escape:    { code: 'Escape',    key: 'Escape', keyCode: 27 },
  Digit1:    { code: 'Digit1',    key: '1',      keyCode: 49 },
  Digit2:    { code: 'Digit2',    key: '2',      keyCode: 50 },
  Digit3:    { code: 'Digit3',    key: '3',      keyCode: 51 },
  Digit4:    { code: 'Digit4',    key: '4',      keyCode: 52 },
}

function dispatch(type: 'keydown' | 'keyup', name: VirtualKeyName): void {
  const def = KEY_MAP[name]
  const event = new KeyboardEvent(type, {
    code: def.code,
    key: def.key,
    keyCode: def.keyCode,
    which: def.keyCode,
    bubbles: true,
    cancelable: true,
  })
  window.dispatchEvent(event)
}

export function virtualKeyDown(name: VirtualKeyName): void {
  dispatch('keydown', name)
}

export function virtualKeyUp(name: VirtualKeyName): void {
  dispatch('keyup', name)
}

/** Fire keydown then keyup on the next frame — for tap-style buttons. */
export function virtualKeyTap(name: VirtualKeyName): void {
  dispatch('keydown', name)
  // Release next frame so the keyboard.update() snapshot registers the
  // press before the release. pc.Keyboard's wasPressed() compares the
  // frame's keymap against the previous frame's _lastmap.
  requestAnimationFrame(() => dispatch('keyup', name))
}
