// `bodhiorchard reset` — tear down the stack AND delete its data volumes.
// Destructive: drops postgres_data, repos_data, ssh_data.
import path from "node:path";
import inquirer from "inquirer";
import { preflight } from "../lib/preflight.js";
import { PROJECT_NAME } from "../lib/config.js";
import { compose } from "../lib/docker.js";
import { log } from "../lib/ui.js";

export interface ResetOptions {
  yes: boolean;
}

export async function resetCommand(projectDir: string, opts: ResetOptions): Promise<void> {
  await preflight();
  const dir = path.resolve(projectDir);

  if (!opts.yes) {
    const { confirm } = await inquirer.prompt<{ confirm: boolean }>([
      {
        type: "confirm",
        name: "confirm",
        message: "This deletes the database and all cloned repos for this install. Continue?",
        default: false,
      },
    ]);
    if (!confirm) {
      log.info("Reset cancelled.");
      return;
    }
  }

  const res = await compose(dir, ["-p", PROJECT_NAME, "down", "-v"], { inherit: true });
  if (res.code === 0) log.success("Stack and data volumes removed.");
  else process.exitCode = 1;
}
