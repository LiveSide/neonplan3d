import assert from "node:assert/strict";
import { test } from "node:test";
import type { Furniture } from "./model.ts";
import { householdEntities, isBin, wasteCalendars } from "./household.ts";

// FORK d14tk: pack items as waste bins
const item = (type: string, extra: Partial<Furniture> = {}): Furniture => ({ id: type, type, x: 0, z: 0, rotation: 0, w: 0.4, d: 0.5, h: 0.45, variant: null, ...extra }) as Furniture;

test("a pack item with a kind of waste is a bin and reads its calendar; without one it is not", () => {
  const paper = item("pack:local.garten:sortera_hoch", { bin_kind: "paper", bin_source: "calendar.papier" });
  assert.equal(isBin(paper), true);
  assert.equal(isBin(item("pack:local.garten:sortera_hoch")), false);
  assert.equal(isBin(item("waste_bin")), true);
  assert.equal(isBin(item("sofa", { bin_kind: "paper" })), false);
  assert.deepEqual(wasteCalendars([{ furniture: [paper] }]), ["calendar.papier"]);
  assert.deepEqual(householdEntities(paper), ["calendar.papier", null]);
});
