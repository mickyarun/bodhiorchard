// `bodhiorchard status` — show container state and the access URL.
import path from "node:path";
import { preflight } from "../lib/preflight.js";
import { readConfig, PROJECT_NAME } from "../lib/config.js";
import { compose } from "../lib/docker.js";
import { log } from "../lib/ui.js";

export async function statusCommand(projectDir: string): Promise<void> {
  await preflight();
  const dir = path.resolve(projectDir);
  const config = await readConfig(dir);

  const res = await compose(dir, ["-p", PROJECT_NAME, "ps"], { inherit: true });
  if (res.code !== 0) {
    process.exitCode = 1;
    return;
  }
  log.plain();
  log.info(`Frontend: http://localhost:${config.services.frontend.hostPort}/`);
  log.info(`Backend:  http://localhost:${config.services.backend.hostPort}/`);
}
