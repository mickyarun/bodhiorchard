import { describe, it, expect, afterEach } from "vitest";
import net from "node:net";
import { isPortOpen, findFreePort } from "./ports.js";

let server: net.Server | undefined;

function listen(host: string, port = 0): Promise<number> {
  return new Promise((resolve, reject) => {
    server = net.createServer();
    server.once("error", reject);
    server.listen(port, host, () => {
      resolve((server!.address() as net.AddressInfo).port);
    });
  });
}

afterEach(() => {
  server?.close();
  server = undefined;
});

describe("isPortOpen", () => {
  it("detects a listener bound to all interfaces (0.0.0.0)", async () => {
    const port = await listen("0.0.0.0");
    expect(await isPortOpen(port)).toBe(true);
  });

  // Regression: a 127.0.0.1-only listener (e.g. Vite `npm run dev`) must be
  // detected. The previous bind-on-0.0.0.0 test missed this on macOS.
  it("detects a listener bound only to 127.0.0.1", async () => {
    const port = await listen("127.0.0.1");
    expect(await isPortOpen(port)).toBe(true);
  });

  it("reports an unbound port as free", async () => {
    const port = await listen("127.0.0.1");
    server?.close();
    server = undefined;
    expect(await isPortOpen(port)).toBe(false);
  });
});

describe("findFreePort", () => {
  it("skips a bound port and returns a later free one", async () => {
    const taken = await listen("127.0.0.1");
    const free = await findFreePort(taken);
    expect(free).toBeGreaterThan(taken);
    expect(await isPortOpen(free)).toBe(false);
  });
});
