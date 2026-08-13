"""Persistent sector-cycle scanner used by GitHub Actions and Streamlit."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from config import TENBAGGER_UNIVERSE
from tenbagger_model import evaluate_tenbagger_candidate

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "tenbagger_scan_state.json"
FINAL_PATH = ROOT / "data" / "tenbagger_final_candidates.json"
KST = timezone(timedelta(hours=9))


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(KST)
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST).isoformat(timespec="seconds")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        converted = value.item()
        return _json_value(converted)
    except AttributeError:
        return str(value)


def empty_state(now: datetime | None = None) -> dict[str, Any]:
    stamp = _now_iso(now)
    return {
        "schema_version": 1,
        "cycle_id": stamp[:10],
        "started_at": stamp,
        "updated_at": stamp,
        "next_sector_index": 0,
        "completed_sectors": [],
        "sector_results": {},
        "cycle_complete": False,
        "finalized_at": None,
    }


def load_scan_state(path: Path = STATE_PATH) -> dict[str, Any]:
    return _read_json(path, empty_state())


def load_final_candidates(path: Path = FINAL_PATH) -> dict[str, Any]:
    return _read_json(path, {"schema_version": 1, "status": "not_ready", "candidates": []})


def _candidate_record(stock: dict[str, Any], sector: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "Name", "Region", "_ticker", "Price", "Change", "MarketCap", "Rev_Growth",
        "Earnings_Growth", "Op_Margin", "ROE", "Forward_PER", "PEG", "FCF_Yield",
        "ROIC", "Rule_of_40", "W52_pos", "MA20_gap", "Dilution_YoY",
        "Price_As_Of", "Price_Source",
    )
    record = {field: _json_value(stock.get(field)) for field in fields}
    record.update({"sector": sector, "evaluation": evaluation})
    return record


def scan_sector(
    sector: str,
    fetcher: Callable[..., dict[str, Any]],
    *,
    full_scan: bool,
) -> dict[str, Any]:
    tickers = TENBAGGER_UNIVERSE[sector]
    is_korea = "한국" in sector
    records, failures = [], []
    for query in tickers:
        stock = fetcher(query, is_kr=is_korea, fast_mode=not full_scan)
        stock["Region"] = "한국" if is_korea else "미국"
        evaluation = evaluate_tenbagger_candidate(stock, sector)
        if stock.get("error"):
            failures.append({"query": query, "error": stock.get("error")})
            continue
        if evaluation["quality_pass"] or evaluation["score"] >= 55:
            records.append(_candidate_record(stock, sector, evaluation))
    records.sort(key=lambda item: item["evaluation"]["score"], reverse=True)
    return {
        "sector": sector,
        "scanned_count": len(tickers),
        "success_count": len(tickers) - len(failures),
        "failures": failures,
        "candidates": records[:5],
    }


def run_morning_cycle(
    fetcher: Callable[..., dict[str, Any]],
    *,
    state_path: Path = STATE_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    state = load_scan_state(state_path)
    sectors = list(TENBAGGER_UNIVERSE)
    if state.get("cycle_complete") and not state.get("finalized_at"):
        return state
    if state.get("cycle_complete") or not state.get("cycle_id"):
        state = empty_state(now)

    index = int(state.get("next_sector_index", 0)) % len(sectors)
    sector = sectors[index]
    result = scan_sector(sector, fetcher, full_scan=False)
    minimum_success = max(1, (result["scanned_count"] + 1) // 2)
    if result["success_count"] < minimum_success:
        state["last_error"] = f"{sector}: 데이터 성공률 50% 미만, 다음 실행에서 재시도"
    else:
        state["sector_results"][sector] = result
        completed = list(dict.fromkeys([*state.get("completed_sectors", []), sector]))
        state["completed_sectors"] = completed
        state["next_sector_index"] = index + 1
        state["cycle_complete"] = len(completed) == len(sectors)
        state.pop("last_error", None)
    state["updated_at"] = _now_iso(now)
    _write_json(state_path, state)
    return state


def run_afternoon_finalize(
    fetcher: Callable[..., dict[str, Any]],
    *,
    quote_fetcher: Callable[..., dict[str, Any] | None] | None = None,
    state_path: Path = STATE_PATH,
    final_path: Path = FINAL_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    state = load_scan_state(state_path)
    if not state.get("cycle_complete"):
        return {"status": "cycle_incomplete", "candidates": []}
    if state.get("finalized_at"):
        return load_final_candidates(final_path)

    preliminary = []
    for sector, result in state.get("sector_results", {}).items():
        for candidate in result.get("candidates", []):
            preliminary.append((sector, candidate))

    final_records = []
    seen = set()
    for sector, candidate in preliminary:
        query = candidate.get("_ticker") or candidate.get("Name")
        identity = (candidate.get("Region"), query)
        if not query or identity in seen:
            continue
        seen.add(identity)
        stock = fetcher(query, is_kr=(candidate.get("Region") == "한국"), fast_mode=False)
        stock["Region"] = candidate.get("Region")
        if quote_fetcher is not None and not stock.get("error"):
            quote = quote_fetcher(query, is_kr=(candidate.get("Region") == "한국"))
            if quote and quote.get("price") is not None:
                latest_price = float(quote["price"])
                stock["Price"] = latest_price
                previous_close = quote.get("previous_close")
                if previous_close:
                    stock["Change"] = round((latest_price / float(previous_close) - 1.0) * 100, 2)
                if stock.get("MA20"):
                    stock["MA20_gap"] = round((latest_price / float(stock["MA20"]) - 1.0) * 100, 2)
                stock["Price_As_Of"] = quote.get("as_of")
                stock["Price_Source"] = quote.get("source")
        evaluation = evaluate_tenbagger_candidate(stock, sector)
        if evaluation["eligible"]:
            final_records.append(_candidate_record(stock, sector, evaluation))

    final_records.sort(key=lambda item: item["evaluation"]["score"], reverse=True)
    per_sector: dict[str, int] = {}
    selected = []
    for item in final_records:
        sector = item["sector"]
        if per_sector.get(sector, 0) >= 3:
            continue
        selected.append(item)
        per_sector[sector] = per_sector.get(sector, 0) + 1
        if len(selected) >= 12:
            break

    payload = {
        "schema_version": 1,
        "status": "ready",
        "cycle_id": state.get("cycle_id"),
        "generated_at": _now_iso(now),
        "candidate_count": len(selected),
        "candidates": selected,
        "notice": "연구 후보이며 ORION 주문 허가와 별개입니다.",
    }
    _write_json(final_path, payload)
    state["finalized_at"] = payload["generated_at"]
    state["updated_at"] = payload["generated_at"]
    _write_json(state_path, state)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("morning", "afternoon"), required=True)
    args = parser.parse_args()
    from data_loader import get_latest_stock_quote, get_stock_data

    result = (run_morning_cycle(get_stock_data) if args.phase == "morning"
              else run_afternoon_finalize(get_stock_data, quote_fetcher=get_latest_stock_quote))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
