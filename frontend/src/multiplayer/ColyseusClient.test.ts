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
 * The house, coffee bar and cafeteria rooms verify a JWT on join and match
 * rooms on their owning keys, so every join must carry the token and the
 * org (plus the owner for a house).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ColyseusClient, type RoomJoinUser } from './ColyseusClient'

const { joinOrCreateMock } = vi.hoisted(() => ({ joinOrCreateMock: vi.fn() }))

vi.mock('@colyseus/sdk', () => ({
  Client: class Client {
    joinOrCreate = joinOrCreateMock
  },
  Room: class Room {},
}))

const user: RoomJoinUser = { userId: 'u-1', name: 'Ana', characterModel: 'm', token: 'jwt-1' }

function fakeRoom(): object {
  return { onMessage: vi.fn(), onStateChange: vi.fn(), leave: vi.fn(async () => undefined) }
}

afterEach(() => {
  ColyseusClient.destroy()
  joinOrCreateMock.mockReset()
})

describe('ColyseusClient shared-room joins', () => {
  it('joins a house room with the org, the owner and the token', async () => {
    joinOrCreateMock.mockResolvedValue(fakeRoom())

    await ColyseusClient.getInstance('ws://test').joinHouseRoom('org-a', 'owner-1', user)

    expect(joinOrCreateMock).toHaveBeenCalledWith(
      'house',
      expect.objectContaining({ orgId: 'org-a', ownerId: 'owner-1', token: 'jwt-1' }),
    )
  })

  it.each([
    ['coffeebar', (c: ColyseusClient) => c.joinCoffeeBarRoom('org-a', user)],
    ['cafeteria', (c: ColyseusClient) => c.joinCafeteriaRoom('org-a', user)],
  ] as const)('joins the %s room with the org and the token', async (name, join) => {
    joinOrCreateMock.mockResolvedValue(fakeRoom())

    await join(ColyseusClient.getInstance('ws://test'))

    expect(joinOrCreateMock).toHaveBeenCalledWith(
      name,
      expect.objectContaining({ orgId: 'org-a', token: 'jwt-1' }),
    )
  })
})
