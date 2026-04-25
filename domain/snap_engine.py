from __future__ import annotations


class SnapEngine:
    @staticmethod
    def snap_value(value: float, targets: list[float], threshold: float) -> float | None:
        if threshold <= 0:
            return None

        best_target: float | None = None
        best_distance: float | None = None

        for target in targets:
            distance = abs(target - value)
            if distance > threshold:
                continue
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_target = target

        return best_target

    @staticmethod
    def best_move_delta(
        start: float,
        duration: float,
        targets: list[float],
        threshold: float,
    ) -> float | None:
        if threshold <= 0:
            return None

        end = start + duration
        best_delta: float | None = None
        best_distance: float | None = None

        for target in targets:
            for edge_value in (start, end):
                delta = target - edge_value
                distance = abs(delta)
                if distance > threshold:
                    continue
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_delta = delta

        return best_delta
