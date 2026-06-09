// `bodhiorchard logs [service]` — follow container logs.
import path from "node:path";
import { preflight } from "../lib/preflight.js";
import { PROJECT_NAME } from "../lib/config.js";
import { compose } from "../lib/docker.js";

export async function logsCommand(projectDir: string, service?: string): Promise<void> {
  await preflight();
  const dir = path.resolve(projectDir);
  const args = ["-p", PROJECT_NAME, "logs", "-f"];
  if (service) args.push(service);
  const res = await compose(dir, args, { inherit: true });
  if (res.code !== 0) process.exitCode = 1;
}
