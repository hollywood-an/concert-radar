import { describe, expect, it } from "vitest";

import {
  dateParts,
  formatDate,
  formatDistance,
  formatMatch,
  formatPrice,
  formatStatus,
} from "@/lib/format";

describe("formatDate", () => {
  const now = new Date("2026-11-19T12:00:00");

  it("leaves the year out for a show this year", () => {
    expect(formatDate("2026-12-05T19:00:00", now)).toBe("Sat, Dec 5, 7:00 PM");
  });

  it("includes the year for a show in another year", () => {
    expect(formatDate("2027-10-15T19:30:00", now)).toBe("Fri, Oct 15, 2027, 7:30 PM");
  });
});

describe("formatMatch", () => {
  it("is hidden for someone who follows nobody", () => {
    expect(formatMatch(0.5, 0)).toBeNull();
  });

  it("shows the score as a percentage once there are follows", () => {
    expect(formatMatch(0.873, 3)).toBe("87% match");
  });

  it("stays between 0 and 100", () => {
    expect(formatMatch(1.2, 1)).toBe("100% match");
    expect(formatMatch(-0.1, 1)).toBe("0% match");
  });
});

describe("formatDistance", () => {
  it("rounds to a tenth of a mile and calls very short distances nearby", () => {
    expect(formatDistance(1609.34 * 3.44)).toBe("3.4 mi");
    expect(formatDistance(50)).toBe("nearby");
  });
});

describe("formatPrice", () => {
  it("returns null without price data, a single price, or a range", () => {
    expect(formatPrice(null, null)).toBeNull();
    expect(formatPrice(3500, 3500)).toBe("$35");
    expect(formatPrice(3500, 6000)).toBe("$35–$60");
  });
});

describe("dateParts", () => {
  const now = new Date("2026-11-19T12:00:00");

  it("splits a date for a ticket stub and drops the current year", () => {
    expect(dateParts("2026-12-05T19:00:00", now)).toEqual({
      month: "Dec",
      day: "5",
      weekday: "Sat",
      year: null,
      time: "7:00 PM",
    });
  });

  it("keeps the year for a show in another year", () => {
    expect(dateParts("2027-02-25T18:30:00", now).year).toBe("2027");
  });
});

describe("formatStatus", () => {
  it("turns an API status into sentence case", () => {
    expect(formatStatus("on_sale")).toBe("On sale");
    expect(formatStatus("announced")).toBe("Announced");
  });
});
