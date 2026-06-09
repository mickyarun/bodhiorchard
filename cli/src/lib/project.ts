// Materializes the generated artifacts (docker-compose.yml + .env) for a
// project directory from its config and secrets. Single writer used by both
// `init` (fresh secrets) and `start`/`update` (secrets recovered from .env).
import fs from "fs-extra";
import path from "node:path";
import type { ProjectConfig } from "./config.js";
import { renderComposeFile } from "./compose.js";
import { renderEnvFile, parseSecretsFromEnv } from "./env.js";
import type { InfraSecrets } from "./secrets.js";

export const COMPOSE_FILE = "docker-compose.yml";
export const ENV_FILE = ".env";
export const GITIGNORE_FILE = ".gitignore";

// The .env holds the at-rest encryption key and JWT secret. If the install dir
// is (or becomes) a git repo, this keeps those out of version control.
const GITIGNORE_CONTENTS = "# Bodhiorchard install — never commit local secrets.\n.env\n";

export function composeFilePath(projectDir: string): string {
  return path.join(projectDir, COMPOSE_FILE);
}

export function envFilePath(projectDir: string): string {
  return path.join(projectDir, ENV_FILE);
}

/** Write docker-compose.yml and .env. The .env is chmod 600 because it holds
 *  the at-rest encryption key and JWT secret. */
export async function materialize(
  projectDir: string,
  config: ProjectConfig,
  secrets: InfraSecrets,
): Promise<void> {
  await fs.ensureDir(projectDir);
  await fs.writeFile(composeFilePath(projectDir), renderComposeFile(config));
  const env = envFilePath(projectDir);
  await fs.writeFile(env, renderEnvFile(config, secrets), { mode: 0o600 });
  // `mode` only applies when the file is created; chmod again so a re-render
  // over an existing (possibly 0644) .env still locks the secrets down.
  await fs.chmod(env, 0o600);

  // Write a .gitignore once; don't clobber a user's edits on re-render.
  const gitignore = path.join(projectDir, GITIGNORE_FILE);
  if (!(await fs.pathExists(gitignore))) await fs.writeFile(gitignore, GITIGNORE_CONTENTS);
}

/** Recover the once-generated secrets from an existing .env. Throws if the file
 *  is missing or incomplete, since regenerating them would orphan encrypted
 *  data and break JWT/bridge auth. */
export async function loadSecrets(projectDir: string): Promise<InfraSecrets> {
  const file = envFilePath(projectDir);
  if (!(await fs.pathExists(file))) {
    throw new Error(`Missing ${ENV_FILE} in ${projectDir}. Run \`bodhiorchard init\` first.`);
  }
  const secrets = parseSecretsFromEnv(await fs.readFile(file, "utf8"));
  if (!secrets) {
    throw new Error(
      `${ENV_FILE} is missing one or more secrets. Restore it from backup — ` +
        `regenerating would orphan encrypted data.`,
    );
  }
  return secrets;
}
