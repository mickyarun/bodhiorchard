// Terminal presentation helpers: colours, spinners, and cross-platform browser
// opening. Kept dependency-light so commands stay readable.
import { spawn } from "node:child_process";
import chalk from "chalk";
import ora, { type Ora } from "ora";

export const log = {
  info: (msg: string): void => console.log(chalk.cyan("i"), msg),
  step: (msg: string): void => console.log(chalk.blue("→"), msg),
  success: (msg: string): void => console.log(chalk.green("✓"), msg),
  warn: (msg: string): void => console.warn(chalk.yellow("!"), msg),
  error: (msg: string): void => console.error(chalk.red("✗"), msg),
  plain: (msg = ""): void => console.log(msg),
};

export function banner(): void {
  console.log();
  console.log(chalk.bold.green("  Bodhiorchard"));
  console.log(chalk.dim("  AI-native software development operations, running locally."));
  console.log();
}

export function spinner(text: string): Ora {
  return ora({ text, spinner: "dots" });
}

/** Open a URL in the default browser. Best-effort: failures are swallowed since
 *  the caller always prints the URL as a fallback. Honours CI / NO_BROWSER. */
export function openBrowser(url: string): void {
  if (process.env.CI || process.env.NO_BROWSER) return;
  const command =
    process.platform === "darwin"
      ? "open"
      : process.platform === "win32"
        ? "cmd"
        : "xdg-open";
  const args = process.platform === "win32" ? ["/c", "start", "", url] : [url];
  try {
    const child = spawn(command, args, { stdio: "ignore", detached: true });
    child.on("error", () => {});
    child.unref();
  } catch {
    // Ignored — the URL is printed by the caller regardless.
  }
}
