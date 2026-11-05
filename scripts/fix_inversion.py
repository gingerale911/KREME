from pathlib import Path

app_path = Path("KREME/frontend/src/App.tsx")
content = app_path.read_text(encoding="utf-8")

old_project = """    const project = (point: Position) => ({
      x: offsetX + (point.x - minX + padX) * scale,
      y: height - offsetY - (point.z - minZ + padZ) * scale,
    });"""

new_project = """    const project = (point: Position) => ({
      x: offsetX + (point.x - minX + padX) * scale,
      y: offsetY + (point.z - minZ + padZ) * scale,
    });"""

old_tip = """          const heading = isNumber(car.heading) ? car.heading : 0;
          const forwardX = Math.sin(heading);
          const forwardZ = Math.cos(heading);
          const magnitude = Math.hypot(forwardX, forwardZ) || 1;
          const arrowScale = isPlayer ? 17 : 10;
          const tip = {
            x: point.x + (forwardX / magnitude) * arrowScale,
            y: point.y - (forwardZ / magnitude) * arrowScale,
          };"""

new_tip = """          const heading = isNumber(car.heading) ? car.heading : 0;
          const forwardX = Math.sin(heading);
          const forwardZ = Math.cos(heading);
          const rotForward = rotateTrackPoints(
            [{ x: forwardX, z: forwardZ }],
            trackOutline?.orientation ?? 0,
          )[0];
          const magnitude = Math.hypot(rotForward.x, rotForward.z) || 1;
          const arrowScale = isPlayer ? 17 : 10;
          const tip = {
            x: point.x + (rotForward.x / magnitude) * arrowScale,
            y: point.y + (rotForward.z / magnitude) * arrowScale,
          };"""

assert old_project in content, "old_project not found"
assert old_tip in content, "old_tip not found"

content = content.replace(old_project, new_project)
content = content.replace(old_tip, new_tip)

app_path.write_text(content, encoding="utf-8")
print("App.tsx successfully updated with un-inverted coordinates and rotated heading arrow!")
