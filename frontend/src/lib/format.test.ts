import { describe, expect, it } from "vitest";

import { formatDateTime, formatNumber, formatPercent } from "./format";

// The day and hour depend on the machine's time zone, so only the shape is fixed.
const RECORDED = "2026-11-02T14:28:07Z";

describe("formatDateTime", () => {
  it("writes Japanese dates as year/month/day with a 24-hour time", () => {
    expect(formatDateTime(RECORDED, "ja")).toMatch(/^2026\/11\/0[123] \d{1,2}:\d{2}$/);
  });

  it("writes English dates with the month's name", () => {
    expect(formatDateTime(RECORDED, "en")).toMatch(/^Nov [123], 2026, \d{1,2}:\d{2}\s[AP]M$/);
  });

  it("follows the UI's language, not the browser's", () => {
    expect(formatDateTime(RECORDED, "ja")).not.toEqual(formatDateTime(RECORDED, "en"));
  });

  it("shows text that is not a date unchanged", () => {
    expect(formatDateTime("not a date", "ja")).toBe("not a date");
  });
});

describe("formatPercent", () => {
  it("rounds to a whole percent", () => {
    expect(formatPercent(0.574)).toBe("57%");
  });
});

describe("formatNumber", () => {
  it("formats numbers in English and Japanese", () => {
    expect(formatNumber(1234567, "en")).toBe("1,234,567");
    expect(formatNumber(1234567, "ja")).toBe("1,234,567");
  });
});
