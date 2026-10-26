import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parse } from "jsonc-parser";

const site = join(dirname(fileURLToPath(import.meta.url)), "..");
const workerName = "yhei-diary-emdash";
const accountId = "7255fd8ded983ed62a629fe7bd775440";
const mode = process.argv[2];
const dryRun = process.argv.includes("--dry-run");
if (!["pause", "resume"].includes(mode)) {
  console.error("Usage: node scripts/site-control.mjs pause|resume [--dry-run]");
  process.exit(2);
}
function config(path) {
  const result = parse(readFileSync(join(site, path), "utf8"));
  if (!result || result.name !== workerName || result.account_id !== accountId) throw new Error(`Unexpected Worker target in ${path}`);
  return result;
}
function routeValue(value) { return JSON.stringify(value ?? null); }
function assertRouting(normal, pause) {
  for (const key of ["route", "routes", "workers_dev", "preview_urls"]) {
    if (routeValue(normal[key]) !== routeValue(pause[key])) throw new Error(`Routing mismatch: ${key}`);
  }
  if (normal.preview_urls !== false) throw new Error("Version URLs must be disabled before deployment");
  if (pause.workers_dev !== true) throw new Error("The temporary workers.dev route must remain covered");
}
const normal = config("wrangler.jsonc");
const paused = config("maintenance/wrangler.jsonc");
assertRouting(normal, paused);
const allowed = new Set(["$schema", "name", "account_id", "main", "compatibility_date", "workers_dev", "preview_urls", "triggers", "route", "routes"]);
for (const key of Object.keys(paused)) if (!allowed.has(key)) throw new Error(`Unexpected maintenance config key: ${key}`);
if (JSON.stringify(paused.triggers) !== JSON.stringify({ crons: [] })) throw new Error("Maintenance cron must be disabled explicitly");
function run(command, args) {
  const result = spawnSync(command, args, { cwd: site, stdio: "inherit", shell: false });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
if (mode === "resume") {
  run("npm", ["run", "build"]);
  const built = config("dist/server/wrangler.json");
  assertRouting(normal, built);
}
const target = mode === "pause" ? "maintenance/wrangler.jsonc" : "dist/server/wrangler.json";
if (mode === "pause" && !dryRun) {
  console.log("Checking that the exact Worker already exists before pausing");
  run(join(site, "node_modules/.bin/wrangler"), ["deployments", "list", "--name", workerName, "--json"]);
}
const args = ["deploy", "--config", target, "--strict", "--keep-vars"];
if (dryRun) args.push("--dry-run");
console.log(`${dryRun ? "Local dry run" : "Deploy"}: ${mode} ${workerName}`);
run(join(site, "node_modules/.bin/wrangler"), args);
