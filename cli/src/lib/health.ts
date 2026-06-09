// Post-start readiness polling. Gates on the backend's /health/ endpoint (which
// also reports DB connectivity) and confirms the frontend is serving.
const POLL_INTERVAL_MS = 2000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchOk(url: string, accept: (res: Response) => Promise<boolean>): Promise<boolean> {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
    return await accept(res);
  } catch {
    return false;
  }
}

async function backendHealthy(port: number): Promise<boolean> {
  return fetchOk(`http://127.0.0.1:${port}/health/`, async (res) => {
    if (!res.ok) return false;
    const body = (await res.json().catch(() => null)) as { status?: string } | null;
    return body?.status === "ok";
  });
}

async function frontendServing(port: number): Promise<boolean> {
  return fetchOk(`http://127.0.0.1:${port}/`, async (res) => res.status < 500);
}

/** Poll until both backend and frontend are ready, or the timeout elapses.
 *  Returns true only on full readiness. */
export async function waitForHealth(
  backendPort: number,
  frontendPort: number,
  timeoutMs = 60000,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if ((await backendHealthy(backendPort)) && (await frontendServing(frontendPort))) return true;
    await sleep(POLL_INTERVAL_MS);
  }
  return false;
}
