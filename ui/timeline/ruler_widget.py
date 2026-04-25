from __future__ import annotations


def format_seconds_label(total_seconds: float) -> str:
    ts = max(total_seconds, 0.0)
    minutes, seconds = divmod(int(ts), 60)
    fraction = ts % 1.0
    if fraction > 0.001:
        # Show 1 decimal place if there is a fractional part
        return f"{minutes:02d}:{seconds:02d}.{int(round(fraction * 10))}"
    return f"{minutes:02d}:{seconds:02d}"
