// Thin wrappers around the docker / docker compose CLIs. Detects the v2
// plugin form (`docker compose`) versus the legacy standalone binary
// (`docker-compose`) once and reuses the result.
import { spawn } from "node:child_process";

export interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}

interface RunOptions {
  cwd?: string;
  /** Stream child stdio to the parent terminal (for `up`, `logs -f`, …). */
  inherit?: boolean;
  env?: NodeJS.ProcessEnv;
}

function run(command: string, args: string[], options: RunOptions = {}): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env ?? process.env,
      stdio: options.inherit ? "inherit" : ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk) => (stdout += chunk.toString()));
    child.stderr?.on("data", (chunk) => (stderr += chunk.toString()));
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

let composePrefix: string[] | null = null;

/** Resolve the argv prefix for compose commands, caching the probe. Returns
 *  e.g. ["docker", "compose"] or ["docker-compose"]. */
export async function resolveComposeCommand(): Promise<string[]> {
  if (composePrefix) return composePrefix;
  const v2 = await run("docker", ["compose", "version"]).catch(() => null);
  if (v2 && v2.code === 0) {
    composePrefix = ["docker", "compose"];
    return composePrefix;
  }
  const v1 = await run("docker-compose", ["version"]).catch(() => null);
  if (v1 && v1.code === 0) {
    composePrefix = ["docker-compose"];
    return composePrefix;
  }
  throw new Error(
    "Docker Compose is not available. Install Docker Desktop (or the compose plugin) and retry.",
  );
}

/** Run a compose subcommand against the installer's project namespace. */
export async function compose(
  projectDir: string,
  args: string[],
  options: { inherit?: boolean } = {},
): Promise<RunResult> {
  const [command, ...prefixArgs] = await resolveComposeCommand();
  return run(command, [...prefixArgs, ...args], { cwd: projectDir, inherit: options.inherit });
}

/** Run a one-off `docker` command (used for the throwaway pgvector probe). */
export async function docker(args: string[]): Promise<RunResult> {
  return run("docker", args);
}
