import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as api from "../../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const harnessRoot = join(here, "..", "..");           // test/unit -> harness/
const README = readFileSync(join(harnessRoot, "README.md"), "utf8");
const INDEX_SRC = readFileSync(join(harnessRoot, "src", "index.ts"), "utf8");

/** Names imported from a given module specifier, split into value vs type imports.
 *  Handles `import { a, b }`, inline `import { type T, c }`, and `import type { T, U }`. */
function importsFrom(source: string, spec: string): { value: string[]; type: string[] } {
  const value: string[] = []; const type: string[] = [];
  // Match `import [type] { ... } from "<spec>"` (single or multi-line braces).
  const re = new RegExp(`import\\s+(type\\s+)?(?:[\\w$]+\\s*,\\s*)?\\{([^}]*)\\}\\s+from\\s+["']${spec}["']`, "g");
  for (const m of source.matchAll(re)) {
    const stmtIsType = Boolean(m[1]);
    for (let raw of m[2].split(",")) {
      raw = raw.trim(); if (!raw) continue;
      raw = raw.replace(/\/\*[\s\S]*?\*\//g, "").trim(); if (!raw) continue;
      raw = raw.split(/\s+as\s+/)[0].trim();           // `Foo as Bar` -> Foo
      let isType = stmtIsType;
      if (raw.startsWith("type ")) { isType = true; raw = raw.slice(5).trim(); }
      if (!raw) continue;
      (isType ? type : value).push(raw);
    }
  }
  return { value, type };
}

/** Type-export names from index.ts source (`export type { ... } from "..."`). */
function exportedTypeNames(src: string): Set<string> {
  const out = new Set<string>();
  for (const m of src.matchAll(/export\s+type\s+\{([^}]*)\}/g))
    for (let raw of m[1].split(",")) { raw = raw.trim().split(/\s+as\s+/).pop()!.trim(); if (raw) out.add(raw); }
  return out;
}

const valueExports = new Set(Object.keys(api));
const typeExports = exportedTypeNames(INDEX_SRC);

describe("README import-drift gate", () => {
  it("has teeth: a bogus cc-harness import is detected as not-exported", () => {
    const fixture = `
      import { createHarness, totallyNotARealExport } from "cc-harness";
      import type { HarnessConfig } from "cc-harness";
    `;
    const { value, type } = importsFrom(fixture, "cc-harness");
    expect(value).toContain("createHarness");
    expect(value).toContain("totallyNotARealExport");
    expect(type).toContain("HarnessConfig");
    // the gate's verdict on the bogus name:
    expect(valueExports.has("totallyNotARealExport")).toBe(false);
    // the real ones resolve:
    expect(valueExports.has("createHarness")).toBe(true);
    expect(typeExports.has("HarnessConfig")).toBe(true);
    // hardened: default + named import is not skipped (false-negative guard)
    const dn = importsFrom(`import createHarness, { sneakyBadName } from "cc-harness";`, "cc-harness");
    expect(dn.value).toContain("sneakyBadName");
    // hardened: an inline block comment doesn't corrupt a real name (false-positive guard)
    const cm = importsFrom(`import { createHarness /* main */, resolveOptions } from "cc-harness";`, "cc-harness");
    expect(cm.value).toContain("createHarness");
    expect(cm.value).toContain("resolveOptions");
  });

  it("every cc-harness import in README.md is a real public export", () => {
    const { value, type } = importsFrom(README, "cc-harness");
    expect(value.length).toBeGreaterThan(0);             // non-vacuous: README must actually use the package
    const allExports = new Set([...valueExports, ...typeExports]);
    const badValue = value.filter((n) => !valueExports.has(n));
    const badType = type.filter((n) => !allExports.has(n));
    expect(badValue, `README imports unknown value(s): ${badValue.join(", ")}`).toEqual([]);
    expect(badType, `README imports unknown type(s): ${badType.join(", ")}`).toEqual([]);
  });
});
