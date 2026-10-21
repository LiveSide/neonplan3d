// Guard: an add-on on the UNRELEASED list must not show anywhere public – not in the manuals, the README, the
// changelog or the roadmap. CI fails as soon as one of these texts names it (it happened once: Pool Pro showed
// for two releases). Releasing an add-on means taking it off UNRELEASED first.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { UNRELEASED } from "./features.ts";

const ROOT = join(import.meta.dirname, "..", "..");
const PUBLIC = ["README.md", "CHANGELOG.md", "ROADMAP.md", "docs/manual.md", "docs/anleitung.md"];

/** The names users would read for each gated add-on (case-insensitive). */
const NAMES: Record<string, RegExp> = {
  pool: /pool\s*pro|pro_pool|pool-modul|pool module/i,
  diagnostics: /diagnostics_report|debug[- ]daten|nutzungs- und fehlerberichte|usage and error reports/i,
};

test("unreleased add-ons are named in no public text", () => {
  for (const feature of UNRELEASED) {
    const name = NAMES[feature];
    assert.ok(name, `add a public name pattern for the unreleased add-on "${feature}" to NAMES`);
    for (const file of PUBLIC) {
      const text = readFileSync(join(ROOT, file), "utf8");
      const lines = text.split("\n").map((line, i) => [i + 1, line] as const).filter(([, line]) => name.test(line));
      assert.deepEqual(lines, [], `${file} names the unreleased add-on "${feature}" (lines ${lines.map(([n]) => n).join(", ")})`);
    }
  }
});

test("Pool Pro stays unreleased until it is released on purpose", () => {
  assert.ok(UNRELEASED.includes("pool" as never), "Pool Pro left the UNRELEASED list – only do that when Torsten releases it");
});
