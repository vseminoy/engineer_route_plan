// Deterministic categorical palette for engineer routes/markers, keyed by
// engineer_id so the same engineer always gets the same color. Red is
// reserved for the urgent-priority ring and the danger/status tokens in
// global.css, so it is left out of this rotation.
const ENGINEER_PALETTE = [
  '#2A78D6', // blue
  '#EB6834', // orange
  '#1BAF7A', // aqua
  '#E87BA4', // magenta
  '#4A3AA7', // violet
  '#008300', // green
  '#EDA100' // yellow
];

export function getEngineerColor(engineerId: number): string {
  const index = ((engineerId % ENGINEER_PALETTE.length) + ENGINEER_PALETTE.length) % ENGINEER_PALETTE.length;
  return ENGINEER_PALETTE[index];
}
