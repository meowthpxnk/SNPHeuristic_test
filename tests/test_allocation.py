from pathlib import Path

from app.allocation import Allocator
from app.schemas import RequestCSVRow, SupplyCSVRow

ROOT = Path(__file__).parents[1]

CSV_PLAN = {
    "R-101": 25,
    "R-102": 25,
    "R-103": 25,
    "R-201": 30,
    "R-202": 30,
    "R-203": 30,
    "R-204": 30,
    "R-301": 0,
    "R-302": 10,
    "R-303": 20,
    "R-304": 30,
    "R-401": 20,
    "R-402": 20,
    "R-403": 19,
    "R-404": 19,
    "R-405": 19,
    "R-501": 75,
    "R-502": 60,
    "R-503": 40,
    "R-601": 125,
    "R-602": 280,
    "R-603": 119,
    "R-701": 100,
    "R-702": 0,
    "R-703": 0,
}


def _request(case, request_id, priority, demand, min_lot, rounding) -> RequestCSVRow:
    return RequestCSVRow(
        case_id=case,
        request_id=request_id,
        dest_location="DC",
        priority=priority,
        demand_qty=demand,
        min_lot=min_lot,
        rounding_value=rounding,
    )


def _supply(case, qty, item="ITEM", source="PLANT") -> SupplyCSVRow:
    return SupplyCSVRow(
        case_id=case,
        period="2026-01",
        item=item,
        source_location=source,
        available_qty=qty,
    )


def _granted(requests, supplies) -> dict[str, int]:
    lines = Allocator(requests, supplies).run()
    return {line.request_id: line.allocated for line in lines}


def test_csv_cases_keep_the_shared_stock_plan():
    requests = RequestCSVRow.read(str(ROOT / "data" / "requests.csv"))
    supplies = SupplyCSVRow.read(str(ROOT / "data" / "supply.csv"))
    assert _granted(requests, supplies) == CSV_PLAN


def test_higher_priority_takes_the_budget_before_the_smaller_demand():
    granted = _granted(
        [
            _request("C", "HIGH", 1, 100, 0, 1),
            _request("C", "LOW", 2, 10, 0, 1),
        ],
        [_supply("C", 15)],
    )
    assert granted == {"HIGH": 15, "LOW": 0}


def test_short_lot_below_min_lot_is_not_shipped():
    granted = _granted(
        [_request("C", "R", 1, 50, 30, 10)],
        [_supply("C", 20)],
    )
    assert granted == {"R": 0}


def test_neighbor_remainder_completes_min_lot():
    granted = _granted(
        [
            _request("CASE_A", "RA", 1, 40, 0, 25),
            _request("CASE_B", "RB", 1, 50, 30, 10),
        ],
        [_supply("CASE_A", 100), _supply("CASE_B", 20)],
    )
    assert granted == {"RA": 50, "RB": 70}
