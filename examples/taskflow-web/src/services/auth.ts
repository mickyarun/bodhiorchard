/**
 * Auth helpers for reading the current session from the stored JWT.
 * Keeps token parsing out of presentation components so they can be
 * tested without stubbing localStorage with a valid JWT.
 */

const TOKEN_KEY = 'access_token'

interface JwtClaims {
  sub?: string | number
}

function decodeJwtPayload(token: string): JwtClaims | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(base64)) as JwtClaims
  } catch {
    return null
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getCurrentUserId(): string | null {
  const token = getAccessToken()
  if (!token) return null
  const claims = decodeJwtPayload(token)
  return claims?.sub != null ? String(claims.sub) : null
}
