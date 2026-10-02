import { describe, expect, it } from "vitest";

import { activeFilterCount } from "@/components/FilterDrawer";
import type { FeedFilters } from "@/types";

const NO_FILTERS: FeedFilters = { dateRange: null, genres: [], maxDistance: null, maxPrice: null };

describe("activeFilterCount", () => {
  it("is zero when no filter is set", () => {
    expect(activeFilterCount(NO_FILTERS)).toBe(0);
  });

  it("counts each kind of filter once", () => {
    expect(activeFilterCount({ ...NO_FILTERS, dateRange: ["2026-10-01", "2026-10-31"] })).toBe(1);
    expect(activeFilterCount({ ...NO_FILTERS, maxDistance: 16093.4 })).toBe(1);
    expect(activeFilterCount({ ...NO_FILTERS, maxPrice: 5000 })).toBe(1);
  });

  it("counts several genres as one filter", () => {
    expect(activeFilterCount({ ...NO_FILTERS, genres: ["indie", "jazz", "punk"] })).toBe(1);
  });

  it("adds up every active filter", () => {
    expect(
      activeFilterCount({
        dateRange: ["2026-10-01", "2026-10-31"],
        genres: ["indie", "jazz"],
        maxDistance: 16093.4,
        maxPrice: 5000,
      }),
    ).toBe(4);
  });
});
