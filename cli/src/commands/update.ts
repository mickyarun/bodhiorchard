// `bodhiorchard update [--tag X.Y.Z]` — pull newer images and recreate the
// stack. With --tag, pins to a specific release; otherwise tracks :latest.
import path from "node:path";
import { preflight } from "../lib/preflight.js";
import { readConfig, writeConfig, PROJECT_NAME } from "../lib/config.js";
import { materialize, loadSecrets } from "../lib/project.js";
import { compose } from "../lib/docker.js";
import { log } from "../lib/ui.js";

export interface UpdateOptions {
  tag?: string;
}

export async function updateCommand(projectDir: string, opts: UpdateOptions): Promise<void> {
  await preflight();
  const dir = path.resolve(projectDir);

  const config = await readConfig(dir);
  if (opts.tag && opts.tag !== config.imageTag) {
    config.imageTag = opts.tag;
    await writeConfig(dir, config);
    await materialize(dir, config, await loadSecrets(dir));
    log.info(`Pinned image tag to ${opts.tag}.`);
  }

  log.step(`Pulling ${config.imageTag} images…`);
  const pull = await compose(dir, ["-p", PROJECT_NAME, "pull"], { inherit: true });
  if (pull.code !== 0) {
    log.error("Image pull failed.");
    process.exitCode = 1;
    return;
  }
  log.success("Images pulled.");

  const up = await compose(dir, ["-p", PROJECT_NAME, "up", "-d"], { inherit: true });
  if (up.code === 0) log.success("Updated and restarted.");
  else process.exitCode = 1;
}
