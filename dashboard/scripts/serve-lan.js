#!/usr/bin/env node
// Serve the built site (dist/) to other devices on the home network.
//
//   npm run serve:lan                         the Wi-Fi / Ethernet address, port 3001
//   npm run serve:lan -- --host 100.x.y.z     a specific address (e.g. this machine's Tailscale IP)
//   npm run serve:lan -- --port 8080
//
// It binds to one address, not 0.0.0.0, so the site is not exposed on VPN or other interfaces.
// There is no password: anyone on the network who knows the address can open it.
import {spawn} from "node:child_process";
import {existsSync} from "node:fs";
import {networkInterfaces} from "node:os";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
// Interfaces that are not the home network: VPNs, Tailscale, containers and VMs.
const SKIP = /^(lo|wg|tun|tap|utun|tailscale|zt|docker|br-|veth|virbr|vmnet|vboxnet|lxc|podman)/;

function privateIPv4(addr) {
  const [a, b] = addr.split(".").map(Number);
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

function lanAddresses() {
  return Object.entries(networkInterfaces())
    .filter(([name]) => !SKIP.test(name))
    .flatMap(([name, addrs]) => (addrs ?? []).filter((a) => a.family === "IPv4" && !a.internal && privateIPv4(a.address)).map((a) => ({name, address: a.address})))
    // Wi-Fi and Ethernet first.
    .sort((x, y) => Number(!/^(wl|en|eth)/.test(x.name)) - Number(!/^(wl|en|eth)/.test(y.name)));
}

function option(name) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : undefined;
}

if (process.argv.includes("-h") || process.argv.includes("--help")) {
  console.log("Usage: npm run serve:lan -- [--host ADDRESS] [--port PORT]");
  process.exit(0);
}
if (!existsSync(join(DIST, "index.html"))) {
  console.error("serve:lan: no built site in dist/; run `npm run build` (or scripts/refresh-dashboard.sh) first.");
  process.exit(2);
}

const found = lanAddresses();
const host = option("host") ?? found[0]?.address;
const port = option("port") ?? "3001";
if (!host) {
  console.error("serve:lan: no home-network address found (is Wi-Fi connected?). Pass one with -- --host ADDRESS.");
  process.exit(2);
}

const vpn = Object.keys(networkInterfaces()).filter((n) => /^(wg|tun|utun)/.test(n));
console.log(`\n  Pouls on your network:  http://${host}:${port}/\n`);
if (found.length > 1 && !option("host")) console.log(`  Other addresses: ${found.slice(1).map((f) => `${f.address} (${f.name})`).join(", ")}`);
console.log("  No password: anyone on this network who knows the address can see your health data.");
console.log("  Stop with Ctrl+C. If another device cannot connect (README > Other devices at home), check:");
console.log(`  same Wi-Fi (not guest or mobile data), the firewall (port ${port}), router client isolation,`);
if (vpn.length) console.log(`  and the VPN (${vpn.join(", ")}): allow local network access in its settings.`);
else console.log("  and any VPN's local network setting.");
console.log("");

// The project's Python (../.venv) also serves the Coach page's live data; plain python3 serves the rest.
const VENV_PY = join(dirname(fileURLToPath(import.meta.url)), "..", "..", ".venv", "bin", "python");
const server = spawn(existsSync(VENV_PY) ? VENV_PY : "python3", [join(dirname(fileURLToPath(import.meta.url)), "serve.py"), "--bind", host, "--port", port, "--directory", DIST], {stdio: "inherit"});
server.on("exit", (code) => process.exit(code ?? 0));
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => server.kill(sig));
