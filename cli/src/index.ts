#!/usr/bin/env node
// Entry point: wires subcommands to commander and centralises error handling.
import { createRequire } from "node:module";
import { Command } from "commander";
import { initCommand } from "./commands/init.js";
import { startCommand } from "./commands/start.js";
import { stopCommand } from "./commands/stop.js";
import { statusCommand } from "./commands/status.js";
import { logsCommand } from "./commands/logs.js";
import { resetCommand } from "./commands/reset.js";
import { updateCommand } from "./commands/update.js";
import { AbortError } from "./lib/resolve.js";
import { PreflightError } from "./lib/preflight.js";
import { log } from "./lib/ui.js";

const require = createRequire(import.meta.url);
const { version } = require("../package.json") as { version: string };

const DEFAULT_DIR = "bodhiorchard";

/** Run a command, translating expected failures into clean exits and unexpected
 *  ones into a single error line (no stack spew). */
async function run(action: () => Promise<void>): Promise<void> {
  try {
    await action();
  } catch (err) {
    if (err instanceof AbortError) {
      log.info("Aborted.");
      process.exit(1);
    }
    const message = err instanceof PreflightError || err instanceof Error ? err.message : String(err);
    log.error(message);
    process.exit(1);
  }
}

const program = new Command();
program
  .name("bodhiorchard")
  .description("Pull and run the Bodhiorchard stack locally with one command.")
  .version(version)
  .option("--project-dir <path>", "directory holding the install (defaults to ./bodhiorchard)");

/** Resolve the working directory for a command from the global flag, defaulting
 *  to the current directory (the `init` hint tells users to cd into it). */
function dir(fallback = "."): string {
  return (program.opts().projectDir as string | undefined) ?? fallback;
}

program
  .command("init")
  .argument("[name]", "directory to create the install in", DEFAULT_DIR)
  .description("Scaffold an install: resolve ports, generate secrets, pull images")
  .option("--yes", "non-interactive: auto-remap port conflicts, accept defaults", false)
  .option("--allow-postgres-reuse", "permit reusing an existing Postgres (verified for pgvector)", false)
  .action((name: string, opts: { yes: boolean; allowPostgresReuse: boolean }) =>
    run(() =>
      initCommand(program.opts().projectDir ?? name, {
        yes: opts.yes,
        allowPostgresReuse: opts.allowPostgresReuse,
      }),
    ),
  );

program
  .command("start")
  .description("Start the stack and open the setup wizard")
  .action(() => run(() => startCommand(dir())));

program
  .command("stop")
  .description("Stop the stack (data is preserved)")
  .action(() => run(() => stopCommand(dir())));

program
  .command("status")
  .description("Show container status and access URLs")
  .action(() => run(() => statusCommand(dir())));

program
  .command("logs")
  .argument("[service]", "limit to one service (backend, frontend, …)")
  .description("Follow container logs")
  .action((service?: string) => run(() => logsCommand(dir(), service)));

program
  .command("reset")
  .description("Stop the stack and delete all data volumes (destructive)")
  .option("--yes", "skip the confirmation prompt", false)
  .action((opts: { yes: boolean }) => run(() => resetCommand(dir(), opts)));

program
  .command("update")
  .description("Pull newer images and restart")
  .option("--tag <version>", "pin to a specific release tag instead of latest")
  .action((opts: { tag?: string }) => run(() => updateCommand(dir(), opts)));

program.parseAsync(process.argv);
