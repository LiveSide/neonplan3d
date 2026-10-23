import assert from "node:assert/strict";
import { test } from "node:test";
import { irkHex } from "./setup.ts";

test("a pasted key: hex with or without separators, or Base64; anything else is no key", () => {
  assert.equal(irkHex("00112233445566778899AABBCCDDEEFF"), "00112233445566778899aabbccddeeff");
  assert.equal(irkHex("00:11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff"), "00112233445566778899aabbccddeeff");
  assert.equal(irkHex("ABEiM0RVZneImaq7zN3u/w=="), "00112233445566778899aabbccddeeff");
  assert.equal(irkHex("irk:00112233445566778899aabbccddeeff"), "00112233445566778899aabbccddeeff");
  assert.equal(irkHex("hello"), null);
  assert.equal(irkHex("0011"), null);
});
