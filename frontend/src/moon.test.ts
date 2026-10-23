import { test } from "node:test";
import assert from "node:assert/strict";
import { moonPosition } from "./moon.ts";

// reference: SunCalc's own test, getMoonPosition(2013-03-05 UTC, 50.5, 30.5) = azimuth -0.97840 rad from south, altitude 0.014551 rad
test("moon position matches SunCalc", () => {
  const m = moonPosition(new Date("2013-03-05T00:00:00Z"), 50.5, 30.5);
  assert.ok(Math.abs(m.azimuth - (-0.97840 / (Math.PI / 180) + 180)) < 0.01, String(m.azimuth));
  assert.ok(Math.abs(m.elevation - 0.014551 / (Math.PI / 180)) < 0.01, String(m.elevation));
});
