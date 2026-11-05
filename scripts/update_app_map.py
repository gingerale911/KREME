from pathlib import Path

app_path = Path("KREME/frontend/src/App.tsx")
content = app_path.read_text(encoding="utf-8")

old_bounds = """  const bounds = useMemo(() => {
    const points = [
      ...transformedWorld.trackPoints,
      ...transformedWorld.mappedHistory,
      ...transformedWorld.mappedCars,
    ];"""

new_bounds = """  const bounds = useMemo(() => {
    // If a static track outline is present, use trackPoints as the bounding box
    // so cars project cleanly on the circuit geometry without viewport distortion.
    const points = transformedWorld.trackPoints.length > 0
      ? transformedWorld.trackPoints
      : [
          ...transformedWorld.mappedHistory,
          ...transformedWorld.mappedCars,
        ];"""

old_render = """        {trackOutline && trackSurfacePath && (
          <>
            <path d={trackSurfacePath} fill="rgba(44, 180, 166, 0.12)" stroke="rgba(78, 220, 193, 0.9)" strokeWidth={1.1} />
            <path d={trackRacingLine} fill="none" stroke="rgba(138, 173, 255, 0.72)" strokeWidth={1.2} strokeDasharray="4 4" />
          </>
        )}
        {hasTrack && path && <polyline points={path} className="track-shadow" />}
        {hasTrack && path && <polyline points={path} className="track-line" />}"""

new_render = """        {trackOutline && trackSurfacePath ? (
          <>
            <path d={trackSurfacePath} fill="rgba(44, 180, 166, 0.12)" stroke="rgba(78, 220, 193, 0.9)" strokeWidth={1.1} />
            <path d={trackRacingLine} fill="none" stroke="rgba(138, 173, 255, 0.72)" strokeWidth={1.2} strokeDasharray="4 4" />
          </>
        ) : (
          hasTrack && path && (
            <>
              <polyline points={path} className="track-shadow" />
              <polyline points={path} className="track-line" />
            </>
          )
        )}"""

assert old_bounds in content, "old_bounds not found"
assert old_render in content, "old_render not found"

content = content.replace(old_bounds, new_bounds)
content = content.replace(old_render, new_render)
app_path.write_text(content, encoding="utf-8")
print("Successfully updated App.tsx!")
