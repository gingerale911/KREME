import test from "node:test";
import assert from "node:assert/strict";
import { formatDataReceived } from "../src/dataReceived.ts";

test("received data uses decimal KB, MB and GB at their exact thresholds", () => {
  for (const [bytes, expected] of [
    [0, "0.0 KB"], [250_000, "250.0 KB"], [999_999, "999.9 KB"],
    [1_000_000, "1.0 MB"], [18_600_000, "18.6 MB"],
    [999_999_999, "999.9 MB"], [1_000_000_000, "1.0 GB"],
    [1_200_000_000, "1.2 GB"], [5_000_000_000, "5.0 GB"],
  ]) assert.equal(formatDataReceived(bytes), expected);
});

test("missing or invalid byte totals are not displayed as zero", () => {
  for (const value of [null, undefined, NaN, Infinity, -1]) {
    assert.equal(formatDataReceived(value), "—");
  }
});
