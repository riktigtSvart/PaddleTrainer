/** Durations are amounts of time, not wall clocks (24:00:00 is valid). */
export function durationHMS(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Nincs adat";
  const seconds = Math.round(Math.abs(value));
  return (value < 0 ? "−" : "") + [Math.floor(seconds / 3600), Math.floor(seconds % 3600 / 60), seconds % 60].map(n => String(n).padStart(2, '0')).join(':');
}

/** null is blank; NaN is an incomplete/invalid input and can never be saved. */
export function parseDurationHMS(value: string): number | null {
  if (!value.trim()) return null;
  const parts = /^(\d{1,3}):([0-5]?\d):([0-5]?\d)$/.exec(value.trim());
  return parts ? Number(parts[1]) * 3600 + Number(parts[2]) * 60 + Number(parts[3]) : NaN;
}
