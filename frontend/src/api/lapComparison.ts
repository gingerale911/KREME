
export interface StoredSession {
  sessionId: string;
  sessionUid: string;
  playerCarIndex: number;
  epoch: number;
  trackId: number | null;
  trackLength: number | null;
  startedAt: string | null;
  updatedAt: string | null;
  lapCount: number;
}

export interface StoredLap {
  lapId: string;
  sessionId: string;
  lapNumber: number;
  trackId: number | null;
  trackLength: number | null;
  lapTimeMs: number | null;
  sector1TimeMs: number | null;
  sector2TimeMs: number | null;
  sector3TimeMs: number | null;
  invalid: boolean;
  partial: boolean;
  qualityReasons: string[];
  sampleCount: number;
  avgSpeedKph: number | null;
  maxSpeedKph: number | null;
  avgThrottle: number | null;
  avgBrake: number | null;
}

export interface ComparisonPoint {
  distance: number;
  referenceElapsedTimeMs: number | null;
  comparisonElapsedTimeMs: number | null;
  deltaMs: number | null;
  referenceSpeed: number | null;
  comparisonSpeed: number | null;
  speedDelta: number | null;
  referenceThrottle: number | null;
  comparisonThrottle: number | null;
  throttleDelta: number | null;
  referenceBrake: number | null;
  comparisonBrake: number | null;
  brakeDelta: number | null;
}

export interface LapComparison {
  referenceLapId: string;
  comparisonLapId: string;
  referenceLapTimeMs: number;
  comparisonLapTimeMs: number;
  totalTimeDeltaMs: number;
  commonTrackLength: number;
  gridPoints: number;
  validDeltaPoints: number;
  data: ComparisonPoint[];
}

async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // Use the default error message.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function getStoredSessions(): Promise<StoredSession[]> {
  return apiGet("/api/sessions");
}

export function getSessionLaps(sessionId: string): Promise<StoredLap[]> {
  return apiGet(
    `/api/sessions/${encodeURIComponent(sessionId)}/laps`,
  );
}

export function getLapComparison(
  referenceId: string,
  comparisonId: string,
  gridPoints = 201,
): Promise<LapComparison> {
  const params = new URLSearchParams({
    reference_id: referenceId,
    comparison_id: comparisonId,
    grid_points: String(gridPoints),
  });

  return apiGet(`/api/laps/compare?${params.toString()}`);
}
