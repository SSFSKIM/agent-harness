// Release-gate acceptance: prove the package works WHEN INSTALLED (not just in-repo).
// build -> npm pack -> install the tarball into a throwaway project -> assert the library
// imports, files:["dist"] shipped no src/, and the bin carries the node shebang.
// Needs network access: the temp install pulls the SDK + zod from the registry.
// Uses execFileSync (no shell) so interpolated paths can't be reinterpreted as commands.
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";

const root = process.cwd();
const run = (file, args, opts = {}) => execFileSync(file, args, { stdio: "inherit", ...opts });
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

// 1. build + pack (prepack also builds; the explicit build keeps the step legible)
run("npm", ["run", "build"]);
run("npm", ["pack"]);
const tarball = join(root, `${pkg.name}-${pkg.version}.tgz`);
assert(existsSync(tarball), `expected tarball ${pkg.name}-${pkg.version}.tgz not found`);

const dir = mkdtempSync(join(tmpdir(), "cc-harness-verify-"));
try {
  // 2. install the tarball into a throwaway project
  run("npm", ["init", "-y"], { cwd: dir, stdio: "ignore" });
  run("npm", ["install", tarball], { cwd: dir });
  const pkgDir = join(dir, "node_modules", pkg.name);

  // 3. library smoke: the public exports resolve at runtime
  const probe = join(dir, "probe.mjs");
  writeFileSync(probe, [
    'import * as m from "cc-harness";',
    'const need = ["createHarness","DaemonSupervisor","DaemonServer","daemonRequest","SwarmRuntime","TaskStore"];',
    'const missing = need.filter((k) => typeof m[k] === "undefined");',
    'if (missing.length) { console.error("MISSING exports: " + missing.join(", ")); process.exit(1); }',
    'console.log("library import OK (" + need.length + " exports present)");',
  ].join("\n"));
  run(process.execPath, [probe], { cwd: dir });

  // 4. files:["dist"] smoke: dist shipped, src did not
  assert(existsSync(join(pkgDir, "dist", "index.js")), "installed package missing dist/index.js");
  assert(!existsSync(join(pkgDir, "src")), "installed package leaked src/ (files:[dist] not honored)");

  // 5. bin smoke: exists, non-empty, node shebang
  const bin = join(pkgDir, "dist", "cli.js");
  assert(existsSync(bin), "installed bin dist/cli.js missing");
  const firstLine = readFileSync(bin, "utf8").split("\n", 1)[0];
  assert(firstLine === "#!/usr/bin/env node", `bin shebang wrong: ${JSON.stringify(firstLine)}`);

  console.log("verify-package: PASS");
} finally {
  rmSync(tarball, { force: true });
  rmSync(dir, { recursive: true, force: true });
}
