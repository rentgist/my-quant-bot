"""Safe refresh policy for ORION's market-data snapshot."""

import datetime as dt
from zoneinfo import ZoneInfo


REFRESH_INTERVAL = dt.timedelta(minutes=5)
REQUIRED_SERIES = ("kospi_10y", "usdkrw_10y", "spy_10y", "vix_10y")


def validate_macro_snapshot(snapshot):
    """Return ``(is_valid, reason)`` for a publishable macro snapshot."""
    if not isinstance(snapshot, dict):
        return False, "Invalid collection result"
    missing = []
    for key in REQUIRED_SERIES:
        value = snapshot.get(key)
        if value is None or getattr(value, "empty", True):
            missing.append(key)
    if missing:
        return False, "Missing required market data: " + ", ".join(missing)
    return True, None


def is_market_session(now):
    """Whether Korea or regular US cash equity hours are open (KST)."""
    kst = dt.timezone(dt.timedelta(hours=9))
    if now.tzinfo is None:
        now = now.replace(tzinfo=kst)
    local = now.astimezone(kst)
    clock = local.time()
    korea_open = local.weekday() < 5 and dt.time(9, 0) <= clock < dt.time(15, 30)
    new_york = now.astimezone(ZoneInfo("America/New_York"))
    us_clock = new_york.time()
    us_open = (
        new_york.weekday() < 5
        and dt.time(9, 30) <= us_clock < dt.time(16, 0)
    )
    return korea_open or us_open


def refresh_is_due(last_attempt, now, interval=REFRESH_INTERVAL):
    return last_attempt is None or now - last_attempt >= interval


def collect_if_valid(collector):
    """Collect once and return a non-publishable result without raising."""
    try:
        snapshot = collector()
    except Exception as exc:
        return False, None, f"Collection error: {exc}"
    valid, reason = validate_macro_snapshot(snapshot)
    return valid, snapshot if valid else None, reason
