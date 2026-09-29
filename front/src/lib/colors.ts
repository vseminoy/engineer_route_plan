// Deterministic categorical palette for engineer routes/markers, keyed by
// engineer_id so the same engineer always gets the same color. Red is
// reserved for the urgent-priority ring and the danger/status tokens in
// global.css, so it is left out of this rotation. Engineer sets go up to 30
// brigades (EngineerSetCreateRequest.engineers), so this needs to stay well
// above a typical region's roster (11-13) before it wraps and repeats a
// color; 7 colors wrapped at brigade 8 and produced exact duplicates.
// Ordering keeps every adjacent pair (the case that actually appears
// together on screen, since ids cycle through the array in order) at OKLab
// ΔE >= 9 in both simulated-CVD and normal vision (validated with the
// dataviz skill's palette checker).
const ENGINEER_PALETTE = [
  '#2A78D6', // blue
  '#EB6834', // orange
  '#1BAF7A', // aqua
  '#EDA100', // yellow
  '#E87BA4', // magenta
  '#008300', // green
  '#4A3AA7', // violet
  '#17A2B8', // cyan
  '#B8860B', // goldenrod
  '#6D28D9', // purple
  '#5AA02C', // olive
  '#C2417A', // rose
  '#3B4C9E', // indigo
  '#C0622E' // terracotta
];

export function getEngineerColor(engineerId: number): string {
  const index = ((engineerId % ENGINEER_PALETTE.length) + ENGINEER_PALETTE.length) % ENGINEER_PALETTE.length;
  return ENGINEER_PALETTE[index];
}
