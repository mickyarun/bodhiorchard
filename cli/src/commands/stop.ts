// `bodhiorchard stop` — stop the stack, preserving volumes (data survives).
import path from "node:path";
import { preflight } from "../lib/preflight.js";
import { PROJECT_NAME } from "../lib/config.js";
import { compose } from "../lib/docker.js";
import { log } from "../lib/ui.js";

export async function stopCommand(projectDir: string): Promise<void> {
  await preflight();
  const dir = path.resolve(projectDir);
  const res = await compose(dir, ["-p", PROJECT_NAME, "down"], { inherit: true });
  if (res.code === 0) log.success("Stopped. Data volumes are preserved.");
  else process.exitCode = 1;
}
