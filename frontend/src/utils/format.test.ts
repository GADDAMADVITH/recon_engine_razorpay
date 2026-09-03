import { describe, expect, it } from "vitest";
import { formatExceptionLabel, formatPaise, formatPercent } from "./format";

describe("format utils", () => {
  it("formats paise as INR currency", () => {
    expect(formatPaise(100000)).toContain("1,000");
  });

  it("formats percent values", () => {
    expect(formatPercent(1)).toBe("100.0%");
  });

  it("formats exception enums as sentence case", () => {
    expect(formatExceptionLabel("MISSING_SETTLEMENT")).toBe("Missing settlement");
    expect(formatExceptionLabel("TIMESTAMP_WITHIN_TOLERANCE")).toBe("Timestamp within tolerance");
    expect(formatExceptionLabel("REFUND_NOT_REFLECTED")).toBe("Refund not reflected");
  });
});
