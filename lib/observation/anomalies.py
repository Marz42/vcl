"""Pure bounded statistical detectors. No I/O, transports or mutation hooks."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime
from statistics import median

MIN_SAMPLES, MAX_SAMPLES, MIN_SPAN = 20, 60, 540
WINDOW, MAX_GAP = 3600, 90
RESTART_WINDOW, RESTART_LIMIT = 300, 3
NETWORK_FLOOR = 1024 * 1024
REASONS = ("COLD", "READY", "MISSING", "STALE", "RESET", "NO_NEW_SAMPLE")


def number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= 2**63 - 1 else None
    except OverflowError:
        return None


def timestamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return number(stamp.timestamp()) if stamp.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return None


def clean_series(value):
    value = value if isinstance(value, dict) else {}
    points = value.get("points")
    out = []
    if isinstance(points, list) and len(points) <= MAX_SAMPLES:
        for point in points:
            if (isinstance(point, list) and len(point) == 2 and number(point[0]) is not None
                    and number(point[1]) is not None and (not out or point[0] > out[-1][0])):
                out.append(list(point))
            else:
                out = []
                break
    return {"points": out, "last_at": number(value.get("last_at")),
            "above_since": number(value.get("above_since"))}


def clean_summary(value):
    value = value if isinstance(value, dict) else {}
    out = {key: value[key] for key in ("value", "baseline_median", "baseline_mad", "threshold", "sample_count",
            "baseline_span_seconds", "above_seconds", "restart_delta", "window_seconds") if number(value.get(key)) is not None}
    if isinstance(value.get("reason"), str) and value["reason"] in REASONS:
        out["reason"] = value["reason"]
    return out


def series(value, at, previous, *, floor, active=False, sustained_seconds=0):
    """Use preceding normal points only, so a sustained spike cannot train itself away."""
    state = clean_series(previous)
    value, at = number(value), number(at)
    summary = {"reason": "MISSING"}
    if value is None or at is None:
        return None, state, summary
    if state["last_at"] is not None and at <= state["last_at"]:
        return None, state, {"reason": "NO_NEW_SAMPLE"}
    if state["last_at"] is not None and at - state["last_at"] > MAX_GAP:
        state = clean_series(None)
    original_points = state["points"]
    points = [point for point in state["points"] if at - point[0] <= WINDOW]
    span = points[-1][0] - points[0][0] if points else 0
    summary = {"value": value, "sample_count": len(points), "baseline_span_seconds": span, "reason": "COLD"}
    state.update(points=points, last_at=at)
    if len(points) < MIN_SAMPLES or span < MIN_SPAN:
        # An expired anomalous baseline must not be replaced with the anomaly.
        if state["above_since"] is not None and len(original_points) >= MIN_SAMPLES:
            center = median(point[1] for point in original_points)
            deviation = median(abs(point[1] - center) for point in original_points)
            threshold = max(floor, 4 * center, center + 6 * deviation)
            if value >= threshold * (.85 if active else 1):
                state["points"] = original_points
                summary.update(reason="STALE", baseline_median=center, baseline_mad=deviation, threshold=threshold)
                return None, state, summary
        state["points"] = (points + [[at, value]])[-MAX_SAMPLES:]
        state["above_since"] = None
        return None, state, summary
    center = median(point[1] for point in points)
    deviation = median(abs(point[1] - center) for point in points)
    threshold = max(floor, 4 * center, center + 6 * deviation)
    high = value >= threshold * (.85 if active else 1)
    state["above_since"] = (state["above_since"] if state["above_since"] is not None else at) if high else None
    duration = at - state["above_since"] if high else 0
    summary.update(reason="READY", baseline_median=center, baseline_mad=deviation,
                   threshold=threshold, above_seconds=duration)
    if not high:
        state["points"] = (points + [[at, value]])[-MAX_SAMPLES:]
    signal = high and (active or duration >= sustained_seconds)
    # A pending sustained anomaly is still normal before its specified duration.
    return signal, state, summary


def clean_state(value):
    value = value if isinstance(value, dict) else {}
    key = value.get("instance_key")
    if not isinstance(key, str) or len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
        key = None
    events = value.get("restart_events")
    clean = []
    if isinstance(events, list) and len(events) <= 32:
        for event in events:
            if (isinstance(event, list) and len(event) == 2 and number(event[0]) is not None
                    and type(event[1]) is int and 0 < event[1] <= 2**63 - 1
                    and (not clean or event[0] > clean[-1][0])):
                clean.append(list(event))
            else:
                clean = []
                break
    count = value.get("restart_count")
    return {"instance_key": key, "observed_at": number(value.get("observed_at")),
            "uptime": number(value.get("uptime")), "restart_count": count if type(count) is int and number(count) is not None else None,
            "restart_at": number(value.get("restart_at")), "restart_events": clean,
            "network": clean_series(value.get("network"))}


def evaluate(record, previous, now, active=()):
    state = clean_state(previous)
    checks = {"SERVICE_RESTART_LOOP": (None, {}), "NETWORK_RATE_ANOMALY": (None, {})}
    summaries = {key: {"reason": "MISSING"} for key in checks}
    observed = timestamp(record.get("observed_at"))
    if (observed is None or not -30 <= now - observed <= 90 or record.get("observation_state") != "OK"
            or ((record.get("health") or {}).get("observation") or {}).get("reason") == "TELEMETRY_STALE"):
        return checks, state, {key: {"reason": "STALE"} for key in checks}, None
    instance = record.get("instance_id")
    if not isinstance(instance, str):
        return checks, state, summaries, None
    key = hashlib.sha256(instance.encode()).hexdigest()
    values = record.get("metrics") or {}
    uptime = number(values.get("uptime_seconds"))
    reset = (key != state["instance_key"] or (uptime is not None and state["uptime"] is not None and uptime < state["uptime"]))
    if reset:
        state = clean_state(None)
    elif state["observed_at"] is not None and observed <= state["observed_at"]:
        return checks, state, {key: {"reason": "NO_NEW_SAMPLE"} for key in checks}, None
    state.update(instance_key=key, observed_at=observed, uptime=uptime)
    rx, tx = number(values.get("rx_bytes_per_second")), number(values.get("tx_bytes_per_second"))
    rate = rx + tx if rx is not None and tx is not None else None
    signal, network, summary = series(rate, observed, state["network"], floor=NETWORK_FLOOR,
                                      active="NETWORK_RATE_ANOMALY" in active)
    state["network"] = network
    checks["NETWORK_RATE_ANOMALY"] = (signal, clean_summary(summary))
    summaries["NETWORK_RATE_ANOMALY"] = clean_summary(summary)
    count = values.get("restart_count")
    lifecycle = None
    if type(count) is int and number(count) is not None:
        previous_count, previous_at = state["restart_count"], state["restart_at"]
        if previous_count is None:
            summaries["SERVICE_RESTART_LOOP"] = {"reason": "COLD"}
        elif count < previous_count or previous_at is None or observed - previous_at > MAX_GAP:
            state["restart_events"] = []
            summaries["SERVICE_RESTART_LOOP"] = {"reason": "RESET"}
        else:
            delta = count - previous_count
            events = [item for item in state["restart_events"] if observed - item[0] <= RESTART_WINDOW]
            if delta:
                events.append([observed, delta])
                lifecycle = {"restart_delta": delta}
            state["restart_events"] = events[-32:]
            total = sum(item[1] for item in state["restart_events"])
            summary = {"reason": "READY", "restart_delta": total, "window_seconds": RESTART_WINDOW}
            checks["SERVICE_RESTART_LOOP"] = (total >= RESTART_LIMIT, summary)
            summaries["SERVICE_RESTART_LOOP"] = summary
        state.update(restart_count=count, restart_at=observed)
    return checks, state, summaries, lifecycle
