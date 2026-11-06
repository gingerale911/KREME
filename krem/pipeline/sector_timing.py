"""Small sector summaries; history scans happen on receipt, never over traces."""
from typing import Any


class SectorTiming:
    def __init__(self):
        self.history: dict[int, list[tuple[int, list[int | None]]]] = {}

    def update(self, packet):
        rows = packet.data['lapHistoryData']
        values = []
        for i, row in enumerate(rows[:int(packet.data['numLaps'])]):
            flags = int(row['lapValidBitFlags'])
            times = []
            for sector in (1, 2, 3):
                ms = int(row[f'sector{sector}TimeMinutesPart']) * 60000 + int(row[f'sector{sector}TimeMSPart'])
                times.append(ms if ms > 0 and flags & (1 << sector) else None)
            values.append((i + 1, times))
        self.history[int(packet.data['carIdx'])] = values

    def snapshot(self, player, player_index: int, records) -> list[dict[str, Any]]:
        personal: list[list[int]] = [[], [], []]
        field: list[list[int]] = [[], [], []]
        for car, rows in self.history.items():
            for lap, times in rows:
                # Do not grade a completed split against itself.
                if car == player_index and lap >= player.current_lap_num:
                    continue
                for i, ms in enumerate(times):
                    if ms:
                        field[i].append(ms)
                        if car == player_index:
                            personal[i].append(ms)
        for record in records:
            if record['lap'] >= player.current_lap_num:
                continue
            for i in range(3):
                valid = record.get('sectorValid', [not record.get('invalid', False)] * 3)
                ms = record.get(f'sector{i + 1}TimeMs')
                if ms and valid[i]:
                    personal[i].append(ms)
                    field[i].append(ms)
        completed = [player.sector1_time_ms, player.sector2_time_ms]
        result = []
        for i in range(3):
            state = 'complete' if i < player.sector else 'current' if i == player.sector else 'upcoming'
            ms = None
            if state == 'complete':
                ms = completed[i] or None
            elif state == 'current' and player.current_lap_num > 0:
                prior = completed[:i]
                if all(value > 0 for value in prior):
                    ms = max(0, player.current_lap_time_ms - sum(prior))
            pb = min(personal[i], default=None)
            sb = min(field[i], default=None)
            grade = 'neutral'
            if ms is not None and state == 'complete' and not player.current_lap_invalid:
                if sb is not None and ms <= sb:
                    grade = 'purple'
                elif pb is not None:
                    grade = 'green' if ms <= pb else 'yellow'
            elif ms is not None and state == 'current' and pb is not None and ms > pb and not player.current_lap_invalid:
                grade = 'yellow'
            result.append(dict(sector=i + 1, state=state, timeMs=ms, grade=grade,
                               personalBestMs=pb, sessionBestMs=sb))
        return result
