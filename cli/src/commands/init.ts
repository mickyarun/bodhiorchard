// `bodhiorchard init [name]` — scaffold a project directory: resolve port
// conflicts, generate secrets, write compose/.env/config, pre-pull images.
import path from "node:path";
import fs from "fs-extra";
import inquirer from "inquirer";
import { preflight } from "../lib/preflight.js";
import { resolveServices } from "../lib/resolve.js";
import { generateSecrets } from "../lib/secrets.js";
import { materialize, loadSecrets, envFilePath } from "../lib/project.js";
import {
  writeConfig,
  configExists,
  CONFIG_VERSION,
  PROJECT_NAME,
  type ProjectConfig,
} from "../lib/config.js";
import { compose } from "../lib/docker.js";
import { banner, log } from "../lib/ui.js";

export interface InitOptions {
  yes: boolean;
  allowPostgresReuse: boolean;
  imageTag: string;
}

export async function initCommand(projectDir: string, opts: InitOptions): Promise<void> {
  banner();
  await preflight();

  const dir = path.resolve(projectDir);

  if ((await configExists(dir)) && !opts.yes) {
    const { proceed } = await inquirer.prompt<{ proceed: boolean }>([
      {
        type: "confirm",
        name: "proceed",
        message: `An install already exists in ${dir}. Re-run init? (regenerates compose/.env, keeps existing secrets and data)`,
        default: false,
      },
    ]);
    if (!proceed) {
      log.info("Nothing changed.");
      return;
    }
  }

  const services = await resolveServices(opts);

  // Reuse the once-generated secrets if re-initialising; otherwise create them.
  const secrets = (await fs.pathExists(envFilePath(dir)))
    ? await loadSecrets(dir)
    : generateSecrets();

  const config: ProjectConfig = {
    version: CONFIG_VERSION,
    project: PROJECT_NAME,
    imageTag: opts.imageTag,
    services,
  };

  await writeConfig(dir, config);
  await materialize(dir, config, secrets);
  log.success(`Wrote docker-compose.yml, .env and .bodhiorchard/config.json to ${dir}`);

  log.step("Pulling Docker images (first run downloads several GB)…");
  const pull = await compose(dir, ["-p", PROJECT_NAME, "pull"], { inherit: true });
  if (pull.code === 0) log.success("Images pulled.");
  else log.warn("Image pull did not complete — `bodhiorchard start` will retry.");

  const rel = path.relative(process.cwd(), dir) || ".";
  log.plain();
  log.info(rel === "." ? "Next: bodhiorchard start" : `Next: cd ${rel} && bodhiorchard start`);
}
