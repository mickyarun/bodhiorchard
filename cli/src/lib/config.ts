// Persisted installer state. Written once by `init` and re-read by every other
// command so host ports and reuse decisions stay consistent across runs.
import fs from "fs-extra";
import path from "node:path";

export const PROJECT_NAME = "bodhiorchard";
export const CONFIG_DIR = ".bodhiorchard";
export const CONFIG_FILE = "config.json";
export const CONFIG_VERSION = 1;

/** A bundled infra service ships as a container; a reused one points at an
 *  already-running server on the host. */
export type InfraService =
  | { mode: "bundled"; hostPort: number }
  | { mode: "reuse"; url: string };

/** App services are always bundled — only the host binding can move. */
export interface AppService {
  hostPort: number;
}

export interface ProjectConfig {
  version: number;
  project: string;
  imageTag: string;
  services: {
    postgres: InfraService;
    redis: InfraService;
    backend: AppService;
    frontend: AppService;
    multiplayer: AppService;
  };
}

export function configPath(projectDir: string): string {
  return path.join(projectDir, CONFIG_DIR, CONFIG_FILE);
}

export async function readConfig(projectDir: string): Promise<ProjectConfig> {
  const file = configPath(projectDir);
  if (!(await fs.pathExists(file))) {
    throw new Error(
      `No installer config found at ${file}. Run \`bodhiorchard init\` first, then run this ` +
        `command from the install directory (or pass --project-dir <path>).`,
    );
  }
  const config = (await fs.readJson(file)) as ProjectConfig;
  if (config.version !== CONFIG_VERSION) {
    throw new Error(
      `Config version ${config.version} is not supported by this CLI (expects ${CONFIG_VERSION}). ` +
        `Re-run \`bodhiorchard init\`.`,
    );
  }
  return config;
}

export async function writeConfig(projectDir: string, config: ProjectConfig): Promise<void> {
  const file = configPath(projectDir);
  await fs.ensureDir(path.dirname(file));
  await fs.writeJson(file, config, { spaces: 2 });
}

export async function configExists(projectDir: string): Promise<boolean> {
  return fs.pathExists(configPath(projectDir));
}
