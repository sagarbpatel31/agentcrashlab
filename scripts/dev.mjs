import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
for (const filename of [".env", ".env.local"]) {
  if (existsSync(filename)) {
    for (const line of readFileSync(filename, "utf8").split("\n")) {
      const match = line.match(/^([A-Z_][A-Z_0-9]*)=(.*)$/);
      if (match && !process.env[match[1]])
        process.env[match[1]] = match[2].trim().replace(/^['"]|['"]$/g, "");
    }
  }
}
const localNode = path.join(root, ".runtime/node_modules/node/bin/node");
const node = existsSync(localNode) ? localNode : process.execPath;
const env = {
  ...process.env,
  ACL_INTERNAL_TOKEN: randomBytes(32).toString("hex"),
  PYTHONPATH: path.join(root, "engine"),
  NEXT_TELEMETRY_DISABLED: "1",
  PATH: path.dirname(node) + path.delimiter + process.env.PATH,
};
const python = existsSync(".venv/bin/python")
  ? path.join(root, ".venv/bin/python")
  : "python3";
const engine = spawn(python, ["-m", "agentcrashlab", "serve"], {
  env,
  stdio: "inherit",
});
let web;
const shutdown = () => {
  web?.kill("SIGTERM");
  engine.kill("SIGTERM");
};
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
engine.on("exit", (code) => {
  if (code) {
    web?.kill();
    process.exitCode = code;
  }
});
let ready = false;
for (let attempt = 0; attempt < 40; attempt++) {
  try {
    const response = await fetch("http://127.0.0.1:8765/health", {
      headers: { Authorization: "Bearer " + env.ACL_INTERNAL_TOKEN },
    });
    if (response.ok) {
      ready = true;
      break;
    }
  } catch {}
  await new Promise((resolve) => setTimeout(resolve, 100));
}
if (!ready) {
  engine.kill();
  throw new Error("Experiment engine did not start on 127.0.0.1:8765");
}
web = spawn(
  node,
  [
    "node_modules/next/dist/bin/next",
    process.argv.includes("--production") ? "start" : "dev",
    "--hostname",
    "127.0.0.1",
    "--port",
    process.env.PORT || "3000",
  ],
  { env, stdio: "inherit" },
);
web.on("exit", (code) => {
  engine.kill();
  process.exitCode = code || 0;
});
