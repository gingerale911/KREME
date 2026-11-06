export function shouldRecordSample(
  lastSampleMarker: string | null,
  marker: string,
  lastGameTime: number | null,
  sessionTime: number,
): { record: boolean; gapBefore: boolean; nextGameTime: number } {
  if (marker === lastSampleMarker) {
    return { record: false, gapBefore: false, nextGameTime: lastGameTime ?? sessionTime };
  }
  const isRewind = lastGameTime !== null && sessionTime < lastGameTime;
  return {
    record: true,
    gapBefore: isRewind,
    nextGameTime: sessionTime,
  };
}

export function formatErsStore(joules: number | null | undefined): string {
  if (typeof joules !== "number" || !Number.isFinite(joules)) return "—";
  return (joules / 1_000_000).toFixed(2);
}

export function formatSuggestedGear(gear: number | null | undefined): string {
  if (typeof gear !== "number" || !Number.isFinite(gear) || gear <= 0) return "—";
  return String(gear);
}

export function formatTyreCompound(
  tyres: { visualCompoundName?: string | null } | null | undefined,
  fallback: number | string | null | undefined,
): string {
  return tyres?.visualCompoundName ?? (fallback == null ? "—" : String(fallback));
}
