import { describe, expect, it } from "vitest";
import { formatPaise, formatPercent } from "./format";

describe("format utils", () => {
  it("formats paise as INR currency", () => {
    expect(formatPaise(100000)).toContain("1,000");
  });

  it("formats percent values", () => {
    expect(formatPercent(1)).toBe("100.0%");
  });
});
