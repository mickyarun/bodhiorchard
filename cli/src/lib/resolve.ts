// Interactive resolution of host ports and infra reuse, producing the
// `services` block of the persisted config. This is where the installer's core
// promise lives: detect an already-running Postgres/Redis and let the user
// remap to a free port or reuse the existing service — instead of crashing on
// a port-bind error.
import inquirer from "inquirer";
import { isPortOpen, findFreePort } from "./ports.js";
import { docker } from "./docker.js";
import { log } from "./ui.js";
import type { AppService, InfraService, ProjectConfig } from "./config.js";

/** Thrown when the user picks "Abort" at a conflict prompt. */
export class AbortError extends Error {
  constructor() {
    super("Setup aborted by user.");
    this.name = "AbortError";
  }
}

export interface ResolveOptions {
  yes: boolean;
  allowPostgresReuse: boolean;
}

const APP_PORTS = { backend: 8000, frontend: 3000, multiplayer: 2567 } as const;
const INFRA_PORTS = { postgres: 5432, redis: 6379 } as const;

/** Rewrite a host-local URL so it is reachable from inside a container. The
 *  host appears right after `@` (with userinfo) or `//` (without); a port,
 *  path, or end-of-string must follow so we don't touch a password or path
 *  segment that merely contains "localhost". */
export function toContainerHost(url: string): string {
  return url.replace(
    /(@|\/\/)(localhost|127\.0\.0\.1)(?=[:/]|$)/,
    "$1host.docker.internal",
  );
}

async function promptHostPort(label: string, defaultPort: number): Promise<number> {
  const suggested = await findFreePort(defaultPort + 1);
  const { hostPort } = await inquirer.prompt<{ hostPort: number }>([
    {
      type: "number",
      name: "hostPort",
      message: `Host port for ${label}:`,
      default: suggested,
      validate: async (value?: number) => {
        if (!value || value < 1 || value > 65535) return "Enter a port between 1 and 65535.";
        return (await isPortOpen(value)) ? `Port ${value} is also in use.` : true;
      },
    },
  ]);
  return hostPort;
}

/** App services are ours — they can only move to another host port. */
async function resolveApp(
  key: keyof typeof APP_PORTS,
  opts: ResolveOptions,
): Promise<AppService> {
  const port = APP_PORTS[key];
  if (!(await isPortOpen(port))) return { hostPort: port };

  if (opts.yes) {
    const hostPort = await findFreePort(port + 1);
    log.warn(`Port ${port} (${key}) in use — using ${hostPort}.`);
    return { hostPort };
  }

  const { action } = await inquirer.prompt<{ action: string }>([
    {
      type: "list",
      name: "action",
      message: `Port ${port} (${key}) is already in use.`,
      choices: [
        { name: "Use a different host port", value: "remap" },
        { name: "Abort", value: "abort" },
      ],
    },
  ]);
  if (action === "abort") throw new AbortError();
  return { hostPort: await promptHostPort(key, port) };
}

async function verifyPgvector(asyncpgUrl: string): Promise<void> {
  const psqlUrl = asyncpgUrl.replace("+asyncpg", "");
  const res = await docker([
    "run",
    "--rm",
    "--add-host=host.docker.internal:host-gateway",
    "postgres:16-alpine",
    "psql",
    psqlUrl,
    "-tAc",
    "SELECT 1 FROM pg_available_extensions WHERE name='vector'",
  ]);
  if (res.code !== 0) {
    throw new Error(`Could not connect to the existing Postgres:\n${res.stderr.trim()}`);
  }
  if (!res.stdout.trim().startsWith("1")) {
    throw new Error(
      "The existing Postgres does not have the pgvector extension available, which " +
        "Bodhiorchard requires (and the connecting role must be able to CREATE EXTENSION). " +
        "Re-run init and choose a different host port so the bundled pgvector image is used instead.",
    );
  }
}

async function reusePostgres(port: number): Promise<InfraService> {
  const { url } = await inquirer.prompt<{ url: string }>([
    {
      type: "input",
      name: "url",
      message: "Connection URL for the existing Postgres:",
      default: `postgresql+asyncpg://bodhiorchard:bodhiorchard@host.docker.internal:${port}/bodhiorchard`,
    },
  ]);
  const containerUrl = toContainerHost(url.trim());
  await verifyPgvector(containerUrl);
  log.success("Verified pgvector is available on the existing Postgres.");
  return { mode: "reuse", url: containerUrl };
}

async function reuseRedis(port: number): Promise<InfraService> {
  const res = await docker([
    "run",
    "--rm",
    "--add-host=host.docker.internal:host-gateway",
    "redis:7-alpine",
    "redis-cli",
    "-h",
    "host.docker.internal",
    "-p",
    String(port),
    "ping",
  ]);
  if (res.code !== 0 || !res.stdout.toUpperCase().includes("PONG")) {
    throw new Error(
      `Could not reach a Redis server on host port ${port}. Make sure it's running, ` +
        `or re-run init and choose a different host port to use the bundled Redis.`,
    );
  }
  log.success(`Verified the existing Redis responds on port ${port}.`);
  return { mode: "reuse", url: `redis://host.docker.internal:${port}` };
}

/** Infra services can be bundled (remap if busy) or reused (point at the host).
 *  Postgres reuse is gated behind --allow-postgres-reuse and verified. */
async function resolveInfra(
  key: keyof typeof INFRA_PORTS,
  opts: ResolveOptions,
): Promise<InfraService> {
  const port = INFRA_PORTS[key];
  if (!(await isPortOpen(port))) return { mode: "bundled", hostPort: port };

  const canReuse = key === "redis" || opts.allowPostgresReuse;

  if (opts.yes) {
    const hostPort = await findFreePort(port + 1);
    log.warn(`Port ${port} (${key}) in use — using ${hostPort} (bundled).`);
    return { mode: "bundled", hostPort };
  }

  const choices = [{ name: "Use a different host port (keep the bundled service)", value: "remap" }];
  if (canReuse) choices.push({ name: "Reuse the service already on this port", value: "reuse" });
  choices.push({ name: "Abort", value: "abort" });

  const { action } = await inquirer.prompt<{ action: string }>([
    {
      type: "list",
      name: "action",
      message: `Port ${port} (${key}) is already in use.`,
      choices,
    },
  ]);
  if (action === "abort") throw new AbortError();
  if (action === "remap") return { mode: "bundled", hostPort: await promptHostPort(key, port) };
  return key === "postgres" ? reusePostgres(port) : reuseRedis(port);
}

export async function resolveServices(opts: ResolveOptions): Promise<ProjectConfig["services"]> {
  return {
    postgres: await resolveInfra("postgres", opts),
    redis: await resolveInfra("redis", opts),
    backend: await resolveApp("backend", opts),
    frontend: await resolveApp("frontend", opts),
    multiplayer: await resolveApp("multiplayer", opts),
  };
}
