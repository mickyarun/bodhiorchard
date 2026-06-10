// Infra secrets generated at install time. These never leave the local machine.
//
// ENCRYPTION_KEY note: the backend treats this value as *input material* for a
// PBKDF2-HMAC-SHA256 derivation (see backend/app/core/encryption.py) before it
// becomes the actual Fernet key — so any high-entropy string works. A 32-byte
// hex string is equivalent in strength to the backend's own secrets.token_hex.
import crypto from "node:crypto";

export interface InfraSecrets {
  SECRET_KEY: string;
  ENCRYPTION_KEY: string;
  COLYSEUS_BRIDGE_SECRET: string;
}

function hex32(): string {
  return crypto.randomBytes(32).toString("hex");
}

export function generateSecrets(): InfraSecrets {
  return {
    SECRET_KEY: hex32(), // JWT signing
    ENCRYPTION_KEY: hex32(), // PBKDF2 input → Fernet key for secrets at rest
    COLYSEUS_BRIDGE_SECRET: hex32(), // shared HMAC between backend and multiplayer
  };
}
