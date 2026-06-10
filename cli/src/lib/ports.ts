// Pure port helpers — no prompts, no lasting side effects.
//
// Detection uses a *connect test* against both loopback families (127.0.0.1 and
// ::1), NOT a bind test. A bind test on 0.0.0.0 looks tempting (Docker publishes
// there) but macOS lets you bind 0.0.0.0:<port> even while something holds
// 127.0.0.1:<port> — so it silently misses loopback-only listeners like a Vite
// dev server (`npm run dev`), the exact case this needs to catch. Connecting to
// both loopback addresses catches anything reachable locally: 0.0.0.0 binds (via
// 127.0.0.1), IPv4 loopback binds, and IPv6-only (::1) binds. Trade-off: a
// listener bound to a specific *non-loopback* IP (e.g. 192.168.1.x:3000) is not
// seen, so `compose up` would fail its bind there — rare for these dev ports and
// far less common than the loopback-only case this targets.
import net from "node:net";

function canConnect(port: number, host: string, timeoutMs = 700): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const done = (open: boolean): void => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(open);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false)); // ECONNREFUSED / EHOSTUNREACH / no IPv6 → free
    socket.connect(port, host);
  });
}

/** True if something is already listening on the port on either loopback family
 *  (so we must not bind it), false if it is free. */
export async function isPortOpen(port: number): Promise<boolean> {
  const [v4, v6] = await Promise.all([
    canConnect(port, "127.0.0.1"),
    canConnect(port, "::1"),
  ]);
  return v4 || v6;
}

/** First free port at or after `start`, scanning a bounded window so a fully
 *  saturated range fails loudly instead of looping forever. */
export async function findFreePort(start: number, span = 200): Promise<number> {
  for (let port = start; port < start + span; port++) {
    if (!(await isPortOpen(port))) return port;
  }
  throw new Error(`No free port found in range ${start}-${start + span - 1}.`);
}
