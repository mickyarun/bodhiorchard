import { describe, it, expect, afterEach } from "vitest";
import net from "node:net";
import { isPortOpen, findFreePort } from "./ports.js";

let server: net.Server | undefined;

function listen(port = 0): Promise<number> {
  return new Promise((resolve, reject) => {
    server = net.createServer();
    server.once("error", reject);
    server.listen(port, "0.0.0.0", () => {
      resolve((server!.address() as net.AddressInfo).port);
    });
  });
}

afterEach(() => {
  server?.close();
  server = undefined;
});

describe("isPortOpen", () => {
  it("reports a bound port as in use", async () => {
    const port = await listen();
    expect(await isPortOpen(port)).toBe(true);
  });

  it("reports an unbound port as free", async () => {
    const port = await listen();
    server?.close();
    server = undefined;
    expect(await isPortOpen(port)).toBe(false);
  });
});

describe("findFreePort", () => {
  it("skips a bound port and returns a later free one", async () => {
    const taken = await listen();
    const free = await findFreePort(taken);
    expect(free).toBeGreaterThan(taken);
    expect(await isPortOpen(free)).toBe(false);
  });
});
