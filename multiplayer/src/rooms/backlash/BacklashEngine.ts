// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import {
  BACKLASH_NO_PROGRESS_TURN_LIMIT,
  BACKLASH_REPETITION_LIMIT,
  applyBacklashMove,
  countPieces,
  createBacklashBoard,
  legalMovesForColor,
  legalMovesForPiece,
  opponentColor,
  positionKey,
  promoteUnderling,
  type BacklashBoard,
  type BacklashColor,
  type BacklashMove,
  type BacklashOutcome,
} from "../../../../shared/minigames/backlash"

export type BacklashEnginePhase = "playing" | "jump" | "promotion" | "finished"

export interface BacklashEngineResult {
  outcome: BacklashOutcome
  winnerColor: BacklashColor | null
  reason: "all_pieces" | "no_legal_moves" | "repetition" | "no_progress" | "timeout" | "disconnect"
}

export interface BacklashMoveResult {
  accepted: boolean
  reason?: "finished" | "wrong_turn" | "invalid_move" | "jump_piece_locked" | "no_legal_moves"
  from?: number
  to?: number
  capturedIndex?: number | null
  capturedColor?: BacklashColor | null
  capturedKind?: "overling" | "underling" | null
  phase?: BacklashEnginePhase
}

export class BacklashEngine {
  board: BacklashBoard = createBacklashBoard()
  turn: BacklashColor = "white"
  phase: BacklashEnginePhase = "playing"
  moveCount = 0
  noProgressTurns = 0
  lockedJumpIndex = -1
  pendingPromotionIndex = -1
  readonly capturedOverlings: Record<BacklashColor, number> = { white: 0, black: 0 }
  result: BacklashEngineResult | null = null

  private jumpVisited = new Set<number>()
  private turnMadeProgress = false
  private readonly repetitions = new Map<string, number>()

  constructor() {
    this.recordPosition()
  }

  reset(): void {
    this.board = createBacklashBoard()
    this.turn = "white"
    this.phase = "playing"
    this.moveCount = 0
    this.noProgressTurns = 0
    this.lockedJumpIndex = -1
    this.pendingPromotionIndex = -1
    this.capturedOverlings.white = 0
    this.capturedOverlings.black = 0
    this.result = null
    this.jumpVisited.clear()
    this.turnMadeProgress = false
    this.repetitions.clear()
    this.recordPosition()
  }

  move(color: BacklashColor, from: number, to: number): BacklashMoveResult {
    if (this.phase === "finished") return { accepted: false, reason: "finished" }
    if (color !== this.turn) return { accepted: false, reason: "wrong_turn" }
    if (this.phase === "promotion") return { accepted: false, reason: "invalid_move" }
    if (this.phase === "jump" && from !== this.lockedJumpIndex) {
      return { accepted: false, reason: "jump_piece_locked" }
    }
    const moving = this.board[from]
    if (!moving || moving.color !== color) return { accepted: false, reason: "invalid_move" }

    const applied = applyBacklashMove(
      this.board,
      { from, to },
      this.phase === "jump"
        ? { jumpOnly: true, excludedLandings: this.jumpVisited }
        : undefined,
    )
    if (!applied) return { accepted: false, reason: "invalid_move" }

    this.board = applied.board
    this.moveCount += 1
    if (this.phase !== "jump") {
      this.jumpVisited = new Set([from])
      this.turnMadeProgress = false
    }
    this.jumpVisited.add(to)

    const capturedIndex = applied.move.isCapture
      ? (applied.move.jumped ?? applied.move.to)
      : null
    if (applied.capturedPiece) {
      this.turnMadeProgress = true
      if (applied.capturedPiece.kind === "overling") {
        this.capturedOverlings[applied.capturedPiece.color] += 1
      }
    }

    if (countPieces(this.board, opponentColor(color)) === 0) {
      this.finish("win", color, "all_pieces")
    } else if (applied.movedPiece.kind === "overling" && applied.move.isJump) {
      const continuations = legalMovesForPiece(this.board, to, {
        jumpOnly: true,
        excludedLandings: this.jumpVisited,
      })
      if (continuations.length > 0) {
        this.phase = "jump"
        this.lockedJumpIndex = to
      } else {
        this.completeTurn()
      }
    } else if (
      applied.promotionAvailable
      && this.capturedOverlings[color] > 0
    ) {
      this.phase = "promotion"
      this.pendingPromotionIndex = to
    } else {
      this.completeTurn()
    }

    return {
      accepted: true,
      from,
      to,
      capturedIndex,
      capturedColor: applied.capturedPiece?.color ?? null,
      capturedKind: applied.capturedPiece?.kind ?? null,
      phase: this.phase,
    }
  }

  endJump(color: BacklashColor): boolean {
    if (this.phase !== "jump" || color !== this.turn) return false
    this.completeTurn()
    return true
  }

  resolvePromotion(color: BacklashColor, accept: boolean): boolean {
    if (this.phase !== "promotion" || color !== this.turn || this.pendingPromotionIndex < 0) {
      return false
    }
    if (accept) {
      if (this.capturedOverlings[color] <= 0) return false
      const promoted = promoteUnderling(this.board, this.pendingPromotionIndex)
      if (!promoted) return false
      this.board = promoted
      this.capturedOverlings[color] -= 1
      this.turnMadeProgress = true
    }
    this.completeTurn()
    return true
  }

  forfeit(loser: BacklashColor, reason: "timeout" | "disconnect"): void {
    if (this.phase === "finished") return
    this.finish("forfeit", opponentColor(loser), reason)
  }

  playAutomaticMove(): BacklashMoveResult {
    if (this.phase === "finished") return { accepted: false, reason: "finished" }
    if (this.phase === "promotion") return { accepted: false, reason: "invalid_move" }
    const move = this.currentLegalMoves().sort(compareAutomaticMoves)[0]
    if (!move) {
      this.finish("win", opponentColor(this.turn), "no_legal_moves")
      return { accepted: false, reason: "no_legal_moves", phase: this.phase }
    }
    return this.move(this.turn, move.from, move.to)
  }

  currentLegalTargets(): number[] {
    return this.currentLegalMoves().map((move) => move.to)
  }

  private currentLegalMoves(): BacklashMove[] {
    if (this.phase === "finished" || this.phase === "promotion") return []
    if (this.phase !== "jump" || this.lockedJumpIndex < 0) {
      return legalMovesForColor(this.board, this.turn)
    }
    return legalMovesForPiece(this.board, this.lockedJumpIndex, {
      jumpOnly: true,
      excludedLandings: this.jumpVisited,
    })
  }

  private completeTurn(): void {
    if (this.phase === "finished") return
    if (this.turnMadeProgress) this.noProgressTurns = 0
    else this.noProgressTurns += 1

    const previousTurn = this.turn
    this.turn = opponentColor(this.turn)
    this.phase = "playing"
    this.lockedJumpIndex = -1
    this.pendingPromotionIndex = -1
    this.jumpVisited.clear()
    this.turnMadeProgress = false

    if (this.noProgressTurns >= BACKLASH_NO_PROGRESS_TURN_LIMIT) {
      this.finish("draw", null, "no_progress")
      return
    }
    if (legalMovesForColor(this.board, this.turn).length === 0) {
      this.finish("win", previousTurn, "no_legal_moves")
      return
    }
    if (this.recordPosition() >= BACKLASH_REPETITION_LIMIT) {
      this.finish("draw", null, "repetition")
    }
  }

  private recordPosition(): number {
    const key = positionKey(this.board, this.turn)
    const count = (this.repetitions.get(key) ?? 0) + 1
    this.repetitions.set(key, count)
    return count
  }

  private finish(
    outcome: BacklashOutcome,
    winnerColor: BacklashColor | null,
    reason: BacklashEngineResult["reason"],
  ): void {
    this.phase = "finished"
    this.lockedJumpIndex = -1
    this.pendingPromotionIndex = -1
    this.result = { outcome, winnerColor, reason }
  }
}

function compareAutomaticMoves(left: BacklashMove, right: BacklashMove): number {
  const capturePriority = Number(right.isCapture) - Number(left.isCapture)
  return capturePriority || left.from - right.from || left.to - right.to
}
