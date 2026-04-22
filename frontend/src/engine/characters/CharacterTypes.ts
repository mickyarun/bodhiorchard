// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CharacterTypes — shared shapes returned by every character factory
 * (currently only KayKit; the legacy Kenney Blocky factory was removed
 * along with the `legacy` pack when character handling was unified).
 */
import type * as pc from 'playcanvas'

export interface CharacterEntity {
  entity: pc.Entity
  memberId: string
  memberName: string
}
