/** Cumulative UDP payload in decimal units (1 KB = 1,000 bytes). */
export function formatDataReceived(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "—";
  const divisor = bytes >= 1_000_000_000 ? 1_000_000_000 : bytes >= 1_000_000 ? 1_000_000 : 1_000;
  const unit = divisor === 1_000_000_000 ? "GB" : divisor === 1_000_000 ? "MB" : "KB";
  // Truncate to avoid showing 1,000.0 KB before the MB threshold is reached.
  return `${(Math.floor(bytes / (divisor / 10)) / 10).toFixed(1)} ${unit}`;
}
