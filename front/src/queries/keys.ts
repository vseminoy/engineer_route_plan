// Only the keys the implemented screens actually read from are defined here.
export const queryKeys = {
  regions: () => ['regions'] as const,
  plan: (planId: number) => ['plan', planId] as const,
  planCompare: (planId: number, baselinePlanId: number) => ['plan', planId, 'compare', baselinePlanId] as const,
  engineerSets: (regionCode: string) => ['engineer-sets', regionCode] as const,
  // engineerSetId omitted (or null) means the region's default set — a third
  // key element of `null` still lets invalidating ['engineers', regionCode]
  // (no third element) match every set of that region.
  engineers: (regionCode: string, engineerSetId: number | null = null) =>
    ['engineers', regionCode, engineerSetId] as const,
  tickets: (regionCode: string) => ['tickets', regionCode] as const
};
