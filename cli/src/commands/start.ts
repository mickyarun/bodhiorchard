// `bodhiorchard start` — bring the stack up from persisted config, wait for
// readiness, then open the in-app setup wizard.
import path from "node:path";
import { preflight } from "../lib/preflight.js";
import { readConfig, PROJECT_NAME } from "../lib/config.js";
import { materialize, loadSecrets } from "../lib/project.js";
import { compose, resolvePullPolicy } from "../lib/docker.js";
import { waitForHealth } from "../lib/health.js";
import { log, spinner, openBrowser } from "../lib/ui.js";

export async function startCommand(projectDir: string): Promise<void> {
  await preflight();
  const dir = path.resolve(projectDir);

  const config = await readConfig(dir);
  const secrets = await loadSecrets(dir);
  // Re-render so any config edits (e.g. a remapped port) take effect; secrets
  // are preserved from the existing .env.
  await materialize(dir, config, secrets);

  // Default: always pull so users track the published images. BODHIORCHARD_PULL
  // can relax this to "missing"/"never" for air-gapped or locally-built images.
  const pull = resolvePullPolicy(process.env.BODHIORCHARD_PULL);
  log.step(pull === "always" ? "Starting Bodhiorchard (pulling any newer images)…" : "Starting Bodhiorchard…");
  const up = await compose(dir, ["-p", PROJECT_NAME, "up", "-d", "--pull", pull], {
    inherit: true,
  });
  if (up.code !== 0) {
    log.error("Failed to start the stack.");
    process.exitCode = 1;
    return;
  }
  log.success("Containers are up.");

  const frontendPort = config.services.frontend.hostPort;
  const setupUrl = `http://localhost:${frontendPort}/setup`;

  const healthSpin = spinner("Waiting for services to become ready…").start();
  const ready = await waitForHealth(config.services.backend.hostPort, frontendPort);
  if (ready) healthSpin.succeed("Bodhiorchard is ready.");
  else healthSpin.warn("Services didn't report ready within 60s — check `bodhiorchard logs`.");

  log.plain();
  log.info(`Open the setup wizard: ${setupUrl}`);
  openBrowser(setupUrl);
}
