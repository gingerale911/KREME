import test from "node:test";
import assert from "node:assert/strict";
import {
  shouldRecordSample,
  formatErsStore,
  formatSuggestedGear,
  formatTyreCompound,
} from "../src/liveSample.ts";

test("shouldRecordSample handles game time rewinds gracefully", () => {
  // Normal progression
  const s1 = shouldRecordSample(null, "f1", null, 10.5);
  assert.equal(s1.record, true);
  assert.equal(s1.gapBefore, false);
  assert.equal(s1.nextGameTime, 10.5);

  const s2 = shouldRecordSample("f1", "f2", 10.5, 10.53);
  assert.equal(s2.record, true);
  assert.equal(s2.gapBefore, false);

  // Rewind / Flashback (session time goes backward)
  const s3 = shouldRecordSample("f2", "f3", 10.53, 7.2);
  assert.equal(s3.record, true);
  assert.equal(s3.gapBefore, true);
  assert.equal(s3.nextGameTime, 7.2);

  // Repeated same frame
  const s4 = shouldRecordSample("f3", "f3", 7.2, 7.2);
  assert.equal(s4.record, false);
});

test("formatters format live values properly", () => {
  assert.equal(formatErsStore(4_000_000), "4.00");
  assert.equal(formatErsStore(2_500_000), "2.50");
  assert.equal(formatErsStore(null), "—");

  assert.equal(formatSuggestedGear(0), "—");
  assert.equal(formatSuggestedGear(4), "4");
  assert.equal(formatSuggestedGear(null), "—");

  assert.equal(formatTyreCompound({ visualCompoundName: "Soft" }, 16), "Soft");
  assert.equal(formatTyreCompound(null, 17), "17");
  assert.equal(formatTyreCompound(null, null), "—");
});
