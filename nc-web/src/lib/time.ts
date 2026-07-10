// Time formatting — a 24h clock stamp for messages. Pure; formatClock takes a Date so tests are
// timezone-deterministic (a locally-constructed Date reads back the same hours/minutes anywhere).
export function formatClock(d: Date): string {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function formatTs(ts: number): string {
  return formatClock(new Date(ts));
}
