// Renders the .env that docker compose interpolates into the compose file.
// Holds the concrete ports, connection URLs and secrets — written chmod 600.
import type { ProjectConfig } from "./config.js";
import type { InfraSecrets } from "./secrets.js";

const BUNDLED_DATABASE_URL =
  "postgresql+asyncpg://bodhiorchard:bodhiorchard@postgres:5432/bodhiorchard";
const BUNDLED_REDIS_URL = "redis://redis:6379";

/** Build the .env contents. Bundled infra uses in-network service DNS for the
 *  backend URLs (host port only affects the host-side binding); reused infra
 *  uses the URL captured at init time. */
export function renderEnvFile(config: ProjectConfig, secrets: InfraSecrets): string {
  const { postgres, redis, backend, frontend, multiplayer } = config.services;
  const lines: string[] = [];

  lines.push(`IMAGE_TAG=${config.imageTag}`);

  if (postgres.mode === "bundled") lines.push(`POSTGRES_HOST_PORT=${postgres.hostPort}`);
  if (redis.mode === "bundled") lines.push(`REDIS_HOST_PORT=${redis.hostPort}`);
  lines.push(`BACKEND_HOST_PORT=${backend.hostPort}`);
  lines.push(`FRONTEND_HOST_PORT=${frontend.hostPort}`);
  lines.push(`MULTIPLAYER_HOST_PORT=${multiplayer.hostPort}`);

  lines.push(`DATABASE_URL=${postgres.mode === "reuse" ? postgres.url : BUNDLED_DATABASE_URL}`);
  lines.push(`REDIS_URL=${redis.mode === "reuse" ? redis.url : BUNDLED_REDIS_URL}`);

  lines.push(`SECRET_KEY=${secrets.SECRET_KEY}`);
  lines.push(`ENCRYPTION_KEY=${secrets.ENCRYPTION_KEY}`);
  lines.push(`COLYSEUS_BRIDGE_SECRET=${secrets.COLYSEUS_BRIDGE_SECRET}`);

  // Configured in the app's setup wizard (AI Engine step), stored encrypted on
  // the org. Left empty here so a key never lands in a plaintext file.
  lines.push("ANTHROPIC_API_KEY=");

  return lines.join("\n") + "\n";
}

/** Recover the generated secrets from an existing .env so re-rendering (e.g. on
 *  `start` after a config port change) preserves them. Secrets are created once
 *  at init and must never be rotated — ENCRYPTION_KEY rotation would orphan
 *  every value encrypted at rest. Returns null if any secret is missing. */
export function parseSecretsFromEnv(envContent: string): InfraSecrets | null {
  const read = (key: string): string | undefined => {
    const match = envContent.match(new RegExp(`^${key}=(.*)$`, "m"));
    return match?.[1]?.trim() || undefined;
  };
  const SECRET_KEY = read("SECRET_KEY");
  const ENCRYPTION_KEY = read("ENCRYPTION_KEY");
  const COLYSEUS_BRIDGE_SECRET = read("COLYSEUS_BRIDGE_SECRET");
  if (!SECRET_KEY || !ENCRYPTION_KEY || !COLYSEUS_BRIDGE_SECRET) return null;
  return { SECRET_KEY, ENCRYPTION_KEY, COLYSEUS_BRIDGE_SECRET };
}
