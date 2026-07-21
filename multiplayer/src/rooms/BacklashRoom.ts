// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { Client, Room } from "colyseus"
import { ArraySchema } from "@colyseus/schema"
import {
  BACKLASH_LOBBY_MS,
  BACKLASH_PROMOTION_MS,
  BACKLASH_RECONNECT_SECONDS,
  BACKLASH_REMATCH_MS,
  BACKLASH_TURN_MS,
  encodeBacklashPiece,
  type BacklashColor,
} from "../../../shared/minigames/backlash"
import {
  BACKLASH_ENCOURAGEMENT_COOLDOWN_MS,
  BACKLASH_MAX_VIEWERS,
  isBacklashEncouragement,
  isBacklashLivePhase,
} from "../../../shared/minigames/backlashSocial"
import { postBacklashResults, verifyUserToken } from "../bridge/BackendClient"
import {
  fireBacklashDispose,
  fireBacklashPhase,
  fireBacklashViewers,
  registerBacklashDeclineHandler,
  unregisterBacklashDeclineHandler,
} from "../bridge/BacklashRegistry"
import {
  BacklashPlayerState,
  BacklashRoomState,
  BacklashViewerState,
} from "../schema/BacklashRoomState"
import { BacklashEngine } from "./backlash/BacklashEngine"

interface BacklashRoomOptions {
  orgId?: string
  hostUserId?: string
  invitedUserId?: string
  userId?: string
  name?: string
  token?: string
  viewer?: boolean
}

interface MovePayload {
  from?: unknown
  to?: unknown
  turnRevision?: unknown
}

function replaceArraySchema<T>(target: ArraySchema<T>, values: readonly T[]): void {
  if (target.length === values.length) {
    values.forEach((value, index) => {
      if (target[index] !== value) target[index] = value
    })
    return
  }
  target.clear()
  target.push(...values)
}

export class BacklashRoom extends Room<{ state: BacklashRoomState }> {
  maxClients = 2 + BACKLASH_MAX_VIEWERS

  private readonly engine = new BacklashEngine()
  private readonly postedMatches = new Set<string>()
  private matchSequence = 0
  private matchStartedAtMs = 0
  private timerGeneration = 0
  private closing = false
  private encouragementSequence = 0
  private readonly lastEncouragementAt = new Map<string, number>()
  private readonly viewerSessions = new Map<string, Set<string>>()

  onCreate(rawOptions: unknown): void {
    const options = (rawOptions ?? {}) as BacklashRoomOptions
    const state = new BacklashRoomState()
    state.orgId = options.orgId ?? ""
    state.hostUserId = options.hostUserId ?? ""
    state.invitedUserId = options.invitedUserId ?? ""
    this.setState(state)
    this.autoDispose = false

    this.onMessage("backlash_move", (client, raw) => this.handleMove(client, raw))
    this.onMessage("backlash_end_jump", (client) => this.handleEndJump(client))
    this.onMessage("backlash_promote", (client, raw) => this.handlePromotion(client, raw))
    this.onMessage("backlash_rematch", (client) => this.handleRematch(client))
    this.onMessage("backlash_cancel", (client) => this.handleCancel(client))
    this.onMessage("backlash_encourage", (client, raw) => this.handleEncouragement(client, raw))

    registerBacklashDeclineHandler(this.roomId, (userId) => this.handleInviteDeclined(userId))
    this.clock.setTimeout(() => {
      if (this.state.phase === "lobby") this.closeLobby("expired")
    }, BACKLASH_LOBBY_MS)
  }

  async onAuth(_client: Client, options: BacklashRoomOptions): Promise<BacklashRoomOptions> {
    if (!options.token) {
      if (process.env.NODE_ENV === "production") throw new Error("auth token required")
      return this.validateJoin(options)
    }
    const verified = await verifyUserToken(options.token, this.state.orgId)
    if (!verified.valid || !verified.user_id || !verified.org_id) {
      throw new Error(verified.reason ?? "invalid auth token")
    }
    if (verified.org_id !== this.state.orgId) throw new Error("token org mismatch")
    const verifiedName = verified.name?.trim()
    const requestedName = options.name?.trim()
    return this.validateJoin({
      ...options,
      userId: verified.user_id,
      name: verifiedName || requestedName || "Player",
    })
  }

  onJoin(
    client: Client,
    options: BacklashRoomOptions,
    authenticated?: BacklashRoomOptions,
  ): void {
    const identity = authenticated ?? options
    const userId = identity.userId!
    const name = (identity.name?.trim() || "Viewer").slice(0, 120)
    const viewer = identity.viewer === true
    client.userData = { userId, name, viewer }
    if (viewer) {
      const sessions = this.viewerSessions.get(userId) ?? new Set<string>()
      sessions.add(client.sessionId)
      this.viewerSessions.set(userId, sessions)
      const spectator = this.state.viewers.get(userId) ?? new BacklashViewerState()
      spectator.userId = userId
      spectator.name = name
      this.state.viewers.set(userId, spectator)
      this.syncViewers()
      return
    }
    let player = this.state.players.get(userId)
    if (!player) {
      player = new BacklashPlayerState()
      player.userId = userId
      player.name = name
      this.state.players.set(userId, player)
    }
    player.connected = true

    if (this.state.players.size === 2 && this.state.phase === "lobby") {
      this.assignInitialColors()
      this.startMatch()
    }
  }

  async onLeave(client: Client, code?: number): Promise<void> {
    if (this.isViewer(client)) {
      if (this.closing) return
      if (code === 1000) {
        this.removeViewer(client)
        return
      }
      try {
        await this.allowReconnection(client, BACKLASH_RECONNECT_SECONDS)
      } catch {
        this.removeViewer(client)
      }
      return
    }
    const userId = this.userIdFor(client)
    const player = userId ? this.state.players.get(userId) : undefined
    if (!player) return
    player.connected = false
    if (this.closing) return

    try {
      await this.allowReconnection(client, BACKLASH_RECONNECT_SECONDS)
      player.connected = true
    } catch {
      if (this.state.phase === "lobby") {
        this.closeLobby("player_left")
        return
      }
      if (this.state.phase !== "finished") {
        const color = this.colorForUser(userId)
        if (color) {
          this.engine.forfeit(color, "disconnect")
          this.finishMatch()
        }
      }
    }
  }

  onDispose(): void {
    this.timerGeneration += 1
    this.viewerSessions.clear()
    unregisterBacklashDeclineHandler(this.roomId)
    fireBacklashDispose(this.roomId)
  }

  declineInvite(userId: string): void {
    this.handleInviteDeclined(userId)
  }

  private validateJoin(options: BacklashRoomOptions): BacklashRoomOptions {
    const userId = options.userId ?? ""
    if (!userId) throw new Error("authenticated user required")
    const participant = userId === this.state.hostUserId || userId === this.state.invitedUserId
    if (participant) return { ...options, userId, viewer: false }
    if (this.state.phase === "lobby") throw new Error("Backlash match is not live yet")
    return { ...options, userId, viewer: true }
  }

  private assignInitialColors(): void {
    const hostIsWhite = Math.random() < 0.5
    const host = this.state.players.get(this.state.hostUserId)
    const invited = this.state.players.get(this.state.invitedUserId)
    if (!host || !invited) return
    host.color = hostIsWhite ? "white" : "black"
    invited.color = hostIsWhite ? "black" : "white"
  }

  private startMatch(): void {
    this.matchSequence += 1
    this.engine.reset()
    this.matchStartedAtMs = Date.now()
    this.state.matchId = `${this.roomId}:${this.matchSequence}`
    this.state.winnerId = ""
    this.state.outcome = ""
    this.state.outcomeReason = ""
    for (const player of this.state.players.values()) player.rematchReady = false
    this.syncState()
    this.scheduleTurnTimeout()
    this.broadcast("backlash_started", { matchId: this.state.matchId })
  }

  private handleMove(client: Client, raw: unknown): void {
    const color = this.colorForClient(client)
    if (!color || typeof raw !== "object" || raw === null) return
    const payload = raw as MovePayload
    if (
      !Number.isInteger(payload.from)
      || !Number.isInteger(payload.to)
      || !Number.isInteger(payload.turnRevision)
      || payload.turnRevision !== this.state.revision
    ) {
      client.send("backlash_error", { reason: "stale_or_invalid_move" })
      return
    }
    const previousTurn = this.engine.turn
    const result = this.engine.move(color, payload.from as number, payload.to as number)
    if (!result.accepted) {
      client.send("backlash_error", { reason: result.reason ?? "invalid_move" })
      return
    }
    this.state.revision = (this.state.revision + 1) & 0xffff
    this.syncState()
    this.broadcast("backlash_move_applied", result)
    if (this.engine.phase === "finished") {
      this.finishMatch()
    } else if (this.engine.phase === "promotion") {
      this.schedulePromotionDefault(color)
    } else if (previousTurn !== this.engine.turn) {
      this.scheduleTurnTimeout()
    }
  }

  private handleEndJump(client: Client): void {
    const color = this.colorForClient(client)
    if (!color || !this.engine.endJump(color)) {
      client.send("backlash_error", { reason: "cannot_end_jump" })
      return
    }
    this.state.revision = (this.state.revision + 1) & 0xffff
    this.syncState()
    this.scheduleTurnTimeout()
  }

  private handlePromotion(client: Client, raw: unknown): void {
    const color = this.colorForClient(client)
    if (!color || typeof raw !== "object" || raw === null) return
    const accept = (raw as { accept?: unknown }).accept
    if (typeof accept !== "boolean" || !this.engine.resolvePromotion(color, accept)) {
      client.send("backlash_error", { reason: "cannot_resolve_promotion" })
      return
    }
    this.state.revision = (this.state.revision + 1) & 0xffff
    this.syncState()
    this.scheduleTurnTimeout()
  }

  private handleRematch(client: Client): void {
    if (this.state.phase !== "finished") return
    const userId = this.userIdFor(client)
    const player = userId ? this.state.players.get(userId) : undefined
    if (!player) return
    player.rematchReady = true
    if ([...this.state.players.values()].every((current) => current.rematchReady && current.connected)) {
      this.swapColors()
      this.startMatch()
    }
  }

  private handleCancel(client: Client): void {
    if (this.state.phase !== "lobby" || this.userIdFor(client) !== this.state.hostUserId) return
    this.closeLobby("cancelled")
  }

  private handleEncouragement(client: Client, raw: unknown): void {
    if (!isBacklashLivePhase(this.state.phase)) {
      client.send("backlash_error", { reason: "encouragement_unavailable" })
      return
    }
    const reaction = typeof raw === "object" && raw !== null
      ? (raw as { reaction?: unknown }).reaction
      : undefined
    if (!isBacklashEncouragement(reaction)) {
      client.send("backlash_error", { reason: "invalid_encouragement" })
      return
    }
    const userId = this.userIdFor(client)
    if (!userId) return
    const now = Date.now()
    const lastSentAt = this.lastEncouragementAt.get(userId) ?? 0
    if (now - lastSentAt < BACKLASH_ENCOURAGEMENT_COOLDOWN_MS) {
      client.send("backlash_error", { reason: "encouragement_rate_limited" })
      return
    }
    this.lastEncouragementAt.set(userId, now)
    this.encouragementSequence += 1
    const userData = client.userData as { name?: string } | undefined
    this.broadcast("backlash_encouragement", {
      id: `${this.roomId}:${this.encouragementSequence}`,
      userId,
      name: userData?.name?.slice(0, 120) || "Teammate",
      reaction,
      createdAtMs: now,
    })
  }

  private handleInviteDeclined(userId: string): void {
    if (this.state.phase !== "lobby" || userId !== this.state.invitedUserId) return
    this.broadcast("backlash_invite_declined", { userId })
    this.closeLobby("declined")
  }

  private scheduleTurnTimeout(): void {
    const generation = ++this.timerGeneration
    const expectedTurn = this.engine.turn
    this.state.turnDeadlineMs = Date.now() + BACKLASH_TURN_MS
    this.clock.setTimeout(() => {
      if (
        generation !== this.timerGeneration
        || this.engine.phase === "finished"
        || this.engine.turn !== expectedTurn
      ) return
      const result = this.engine.playAutomaticMove()
      if (!result.accepted) {
        if (this.engine.result) this.finishMatch()
        return
      }
      this.state.revision = (this.state.revision + 1) & 0xffff
      this.syncState()
      this.broadcast("backlash_move_applied", { ...result, automatic: true })
      if (result.phase === "finished") {
        this.finishMatch()
      } else if (result.phase === "promotion") {
        this.schedulePromotionDefault(expectedTurn)
      } else {
        this.scheduleTurnTimeout()
      }
    }, BACKLASH_TURN_MS)
  }

  private schedulePromotionDefault(color: BacklashColor): void {
    const generation = this.timerGeneration
    const matchId = this.state.matchId
    this.clock.setTimeout(() => {
      if (
        generation !== this.timerGeneration
        || matchId !== this.state.matchId
        || this.engine.phase !== "promotion"
        || this.engine.turn !== color
      ) return
      if (this.engine.resolvePromotion(color, false)) {
        this.state.revision = (this.state.revision + 1) & 0xffff
        this.syncState()
        this.scheduleTurnTimeout()
      }
    }, BACKLASH_PROMOTION_MS)
  }

  private finishMatch(): void {
    const result = this.engine.result
    if (!result) return
    this.timerGeneration += 1
    this.syncState()
    this.state.turnDeadlineMs = 0
    this.state.outcome = result.outcome
    this.state.outcomeReason = result.reason
    this.state.winnerId = result.winnerColor ? this.userIdForColor(result.winnerColor) ?? "" : ""
    void this.postResult()

    const matchId = this.state.matchId
    this.clock.setTimeout(() => {
      if (this.state.matchId === matchId && this.state.phase === "finished") {
        this.closeLobby("rematch_expired")
      }
    }, BACKLASH_REMATCH_MS)
  }

  private async postResult(): Promise<void> {
    const matchId = this.state.matchId
    if (!matchId || this.postedMatches.has(matchId) || !this.engine.result) return
    this.postedMatches.add(matchId)
    const whiteUserId = this.userIdForColor("white")
    const blackUserId = this.userIdForColor("black")
    if (!whiteUserId || !blackUserId) return
    const response = await postBacklashResults({
      matchId,
      roomId: this.roomId,
      orgId: this.state.orgId,
      whiteUserId,
      blackUserId,
      winnerUserId: this.state.winnerId || null,
      outcome: this.engine.result.outcome,
      reason: this.engine.result.reason,
      moveCount: this.engine.moveCount,
      durationMs: Math.max(0, Date.now() - this.matchStartedAtMs),
    })
    this.broadcast("backlash_result", response ?? { recorded: false, players: [] })
  }

  private syncState(): void {
    this.state.phase = this.engine.phase
    fireBacklashPhase(this.roomId, this.state.phase)
    this.state.turnColor = this.engine.turn
    this.state.turnUserId = this.userIdForColor(this.engine.turn) ?? ""
    this.state.lockedJumpIndex = this.engine.lockedJumpIndex
    this.state.pendingPromotionIndex = this.engine.pendingPromotionIndex
    this.state.moveCount = Math.min(0xffff, this.engine.moveCount)
    replaceArraySchema(this.state.board, this.engine.board.map(encodeBacklashPiece))
    replaceArraySchema(this.state.legalTargets, this.engine.currentLegalTargets())
    for (const player of this.state.players.values()) {
      if (player.color === "white" || player.color === "black") {
        player.capturedOverlings = this.engine.capturedOverlings[player.color]
      }
    }
  }

  private swapColors(): void {
    for (const player of this.state.players.values()) {
      player.color = player.color === "white" ? "black" : "white"
    }
  }

  private closeLobby(reason: string): void {
    if (this.closing) return
    this.closing = true
    this.timerGeneration += 1
    this.broadcast("backlash_closed", { reason })
    this.autoDispose = true
    this.clock.setTimeout(() => this.disconnect(), 150)
  }

  private userIdFor(client: Client): string {
    return (client.userData as { userId?: string } | undefined)?.userId ?? ""
  }

  private isViewer(client: Client): boolean {
    return (client.userData as { viewer?: boolean } | undefined)?.viewer === true
  }

  private removeViewer(client: Client): void {
    const userId = this.userIdFor(client)
    const sessions = this.viewerSessions.get(userId)
    if (!sessions?.delete(client.sessionId)) return
    if (sessions.size > 0) return
    this.viewerSessions.delete(userId)
    if (!this.state.viewers.delete(userId)) return
    this.syncViewers()
  }

  private syncViewers(): void {
    const viewerNames = Array.from(this.state.viewers.values(), (viewer) => viewer.name)
    this.state.viewerCount = viewerNames.length
    fireBacklashViewers(this.roomId, viewerNames)
  }

  private colorForClient(client: Client): BacklashColor | null {
    return this.colorForUser(this.userIdFor(client))
  }

  private colorForUser(userId: string): BacklashColor | null {
    const color = this.state.players.get(userId)?.color
    return color === "white" || color === "black" ? color : null
  }

  private userIdForColor(color: BacklashColor): string | null {
    for (const player of this.state.players.values()) {
      if (player.color === color) return player.userId
    }
    return null
  }
}

export { BacklashRoomState }
