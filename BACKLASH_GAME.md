# Backlash two-player mini-game

Implementation checklist and maintenance notes for the real-time Backlash game.
The physical-game rules were taken from the
[Funskool instruction sheet](https://funskoolindia.com/wp-content/uploads/2024/09/Backlash_Instructions.pdf).

## Product rules

- [x] Use an 8 × 8 board with eight Overlings on each back rank and eight
  Underlings directly in front of them.
- [x] Assign colours when both invited players join; White always moves first.
- [x] Let an Overling move one square in any direction.
- [x] Let an Overling jump an adjacent friendly or opposing piece into an empty
  square. An opposing jumped piece is captured; a friendly one remains.
- [x] Lock a chain jump to the same Overling, prevent a landing from being
  revisited in the same chain, and let the player end an available chain early.
- [x] Let an Underling move one square in any direction, but capture only an
  opposing piece on a diagonal by replacing it.
- [x] Offer an optional exchange when an Underling reaches the far rank and its
  owner has a previously captured Overling in reserve.
- [x] Win immediately after removing every opposing piece.

## Digital match safeguards

- [x] Keep the server authoritative; the browser calculates highlights only.
- [x] Reject invalid payloads, wrong-turn actions, stale revisions, illegal
  destinations, wrong-piece chain jumps, and invalid promotion decisions.
- [x] Apply a 60-second turn clock and award a forfeit on timeout.
- [x] Allow 30 seconds for a dropped player to reconnect, then award a forfeit.
- [x] Award a win when the next player has no legal move.
- [x] Declare a draw after the same position occurs three times.
- [x] Declare a draw after 100 turns without a capture or restoration.
- [x] Expire unanswered invitations after five minutes and the rematch offer
  after 30 seconds.
- [x] Make result recording idempotent by authoritative match id.

## Architecture

- [x] Put pure rules and constants in `shared/minigames/backlash.ts` so the
  Colyseus server and browser use one vocabulary without sharing authority.
- [x] Keep mutable match transitions in an isolated `BacklashEngine` with unit
  tests, and transport/lifecycle concerns in `BacklashRoom`.
- [x] Create challenges through the existing authenticated `OrgRoom` and use a
  dedicated, participant-only Colyseus room for each match.
- [x] Persist invitations through the existing notifications system and publish
  decline events through the existing backend-to-Colyseus bridge.
- [x] Store immutable match history separately from org-scoped aggregate stats.
- [x] Expose Backlash through the existing mini-game status and leaderboard APIs.
- [x] Keep challenge, toast, room client, and board view as separate frontend
  modules; reuse the member directory and member picker.

## UI and accessibility

- [x] Provide a responsive board for desktop, tablet, and narrow mobile screens.
- [x] Orient the board toward the local player's colour.
- [x] Animate piece movement, captures, legal targets, timer urgency, connection
  recovery, promotion, and result states.
- [x] Include text labels, focusable board squares, reduced-motion support, and
  colour-independent piece markings.
- [x] Show lobby, reconnecting, chain-jump, promotion, result, rematch, decline,
  cancellation, and expired-room states explicitly.

## Verification

- [x] Unit-test layout, movement, captures, jump chains, promotion, malformed
  inputs, final capture, no-legal-move wins, repetition/no-progress draws,
  forfeits, reset, and invitation parsing.
- [x] Validate backend result combinations, tenant membership, and idempotency.
- [x] Run TypeScript builds, Python linting, migrations checks, and focused test
  suites before merge.
- [x] Complete a two-browser manual smoke test against a migrated local database
  before production deployment.
