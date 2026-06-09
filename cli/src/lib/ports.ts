// Pure port helpers — no prompts, no lasting side effects.
//
// We use a *bind test* (try to listen on 0.0.0.0:<port>) rather than a connect
// probe. `docker run -p X:Y` binds the host side on 0.0.0.0, so a bind test is
// the most accurate predictor of whether compose will be able to claim the
// port: if Node gets EADDRINUSE, Docker would too — regardless of whether the
// existing listener is on IPv4, IPv6, or all interfaces. This closes the gap a
// `127.0.0.1` connect probe (or `nc -z localhost`) leaves for IPv6-only or
// loopback-only listeners.
import net from "node:net";

/** True if the host port is already claimed (so we must not bind it), false if
 *  it is free. Any bind error other than a clean listen is treated as "in use"
 *  so the picker errs toward avoiding a port it cannot prove is free. */
export function isPortOpen(port: number, host = "0.0.0.0"): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => {
      // EADDRINUSE (taken), EACCES (privileged), or anything else: we couldn't
      // claim it, so neither can Docker — treat as unavailable.
      server.close();
      resolve(true);
    });
    server.once("listening", () => {
      server.close(() => resolve(false));
    });
    server.listen(port, host);
  });
}

/** First free port at or after `start`, scanning a bounded window so a fully
 *  saturated range fails loudly instead of looping forever. */
export async function findFreePort(start: number, span = 200): Promise<number> {
  for (let port = start; port < start + span; port++) {
    if (!(await isPortOpen(port))) return port;
  }
  throw new Error(`No free port found in range ${start}-${start + span - 1}.`);
}
