// Infra secrets generated at install time. These never leave the local machine.
//
// ENCRYPTION_KEY note: the backend treats this value as *input material* for a
// PBKDF2-HMAC-SHA256 derivation (see backend/app/core/encryption.py) before it
// becomes the actual Fernet key — so any high-entropy string works. A 32-byte
// hex string is equivalent in strength to the backend's own secrets.token_hex.
//
// HR_ENCRYPTION_KEYS is different: it is used as-is, as a keyring of
// kid:base64 entries holding 32-byte AES-256 keys (backend/app/core/hr_crypto.py).
import crypto from "node:crypto";

export interface InfraSecrets {
  SECRET_KEY: string;
  ENCRYPTION_KEY: string;
  COLYSEUS_BRIDGE_SECRET: string;
  HR_ENCRYPTION_KEYS: string;
}

/** What an existing .env holds: installs from before HR records lack a keyring. */
export type StoredSecrets = Omit<InfraSecrets, "HR_ENCRYPTION_KEYS"> & {
  HR_ENCRYPTION_KEYS?: string;
};

function hex32(): string {
  return crypto.randomBytes(32).toString("hex");
}

/** A one-key HR keyring. Installs from before HR records existed get one on
 *  their next start, which is safe: nothing can be encrypted without it. The
 *  kid is random so keyrings from two installs can be combined. */
export function generateHrKeyring(): string {
  const kid = `k${crypto.randomBytes(3).toString("hex")}`;
  return `${kid}:${crypto.randomBytes(32).toString("base64")}`;
}

export function generateSecrets(): InfraSecrets {
  return {
    SECRET_KEY: hex32(), // JWT signing
    ENCRYPTION_KEY: hex32(), // PBKDF2 input → Fernet key for secrets at rest
    COLYSEUS_BRIDGE_SECRET: hex32(), // shared HMAC between backend and multiplayer
    HR_ENCRYPTION_KEYS: generateHrKeyring(), // AES-256-GCM for employee records
  };
}
