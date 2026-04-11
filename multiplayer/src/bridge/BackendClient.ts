/**
 * BackendClient — Colyseus → backend HTTP client.
 *
 * The Colyseus server calls the backend to:
 *   - Fetch initial org snapshot when an OrgRoom is created
 *   - Verify user JWTs on room join
 *
 * Shared secret authentication via X-Bridge-Secret header.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// Fail-closed in production; allow a dev default for local tooling.
if (process.env.NODE_ENV === "production" && !process.env.COLYSEUS_BRIDGE_SECRET) {
  throw new Error(
    "[BackendClient] COLYSEUS_BRIDGE_SECRET must be set in production. " +
    "Refusing to start with the dev default secret.",
  )
}
const BRIDGE_SECRET = process.env.COLYSEUS_BRIDGE_SECRET ?? "dev-colyseus-bridge-secret"

export interface OrgSnapshotMember {
  user_id: string
  name: string
  character_model: string | null
  presence: "active" | "on_break" | "at_home"
  level?: number
  level_name?: string
}

export interface OrgSnapshotResponse {
  orgId: string
  members: OrgSnapshotMember[]
  repos: Array<{ repo_name: string; growth_stage: number }>
}

export interface TokenVerification {
  valid: boolean
  user_id?: string
  org_id?: string
  name?: string
}

const FETCH_TIMEOUT_MS = 3000

/** Fetch an org snapshot from the backend. Returns null on failure. */
export async function fetchOrgSnapshot(orgId: string): Promise<OrgSnapshotResponse | null> {
  try {
    const url = `${BACKEND_URL}/api/v1/internal/colyseus/org-snapshot/${orgId}`
    const response = await fetch(url, {
      method: "GET",
      headers: {
        "X-Bridge-Secret": BRIDGE_SECRET,
      },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) {
      console.warn(`[BackendClient] org-snapshot failed: ${response.status} ${response.statusText}`)
      return null
    }
    return (await response.json()) as OrgSnapshotResponse
  } catch (err) {
    console.warn(`[BackendClient] org-snapshot error:`, err)
    return null
  }
}

/** Verify a user JWT against the backend. */
export async function verifyUserToken(
  token: string,
  orgId: string,
): Promise<TokenVerification> {
  try {
    const url = `${BACKEND_URL}/api/v1/internal/colyseus/verify-token`
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-Bridge-Secret": BRIDGE_SECRET,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token, org_id: orgId }),
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) return { valid: false }
    return (await response.json()) as TokenVerification
  } catch (err) {
    console.warn(`[BackendClient] verify-token error:`, err)
    return { valid: false }
  }
}
