// Cache keys per 06_spec_frontend.md §4. Only the keys the implemented
// screens actually read from are defined here.
export const queryKeys = {
  regions: () => ['regions'] as const,
  plan: (planId: number) => ['plan', planId] as const,
  engineers: (regionCode: string) => ['engineers', regionCode] as const,
  tickets: (regionCode: string) => ['tickets', regionCode] as const
};
