// Environment checks run before any command that touches Docker. Fails fast
// with actionable messages instead of letting compose error out cryptically.
import { docker, resolveComposeCommand } from "./docker.js";

export class PreflightError extends Error {}

/** Verify the docker CLI exists, the daemon is reachable, and compose is
 *  available. Throws PreflightError with a fix-it hint on the first failure. */
export async function preflight(): Promise<void> {
  const version = await docker(["--version"]).catch(() => null);
  if (!version || version.code !== 0) {
    throw new PreflightError(
      "Docker is not installed or not on PATH. Install Docker Desktop: https://docs.docker.com/get-docker/",
    );
  }

  const info = await docker(["info"]).catch(() => null);
  if (!info || info.code !== 0) {
    throw new PreflightError(
      "Docker is installed but the daemon isn't running. Start Docker Desktop (or `dockerd`) and retry.",
    );
  }

  // Surfaces the compose-missing message from resolveComposeCommand.
  await resolveComposeCommand();
}
