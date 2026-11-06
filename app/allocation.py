from logging import getLogger

from app.schemas import RequestCSVRow, SupplyCSVRow
from app.utils import timer

logger = getLogger(__name__)


def _item_id(supply: SupplyCSVRow) -> str:
    return f"{supply.item}-{supply.source_location}"


class AllocationLine:
    def __init__(self, request: RequestCSVRow, supply: SupplyCSVRow) -> None:
        for name in (
            "case_id",
            "request_id",
            "dest_location",
            "priority",
            "demand_qty",
            "min_lot",
            "rounding_value",
        ):
            setattr(self, name, getattr(request, name))
        self.item_id = _item_id(supply)
        self.allocated = 0

    @property
    def step(self) -> int:
        return self.rounding_value or 1

    def blocked(self) -> bool:
        return self.demand_qty <= 0 or self.min_lot < 0 or self.rounding_value < 0


def _room_upto(line: AllocationLine, limit: int) -> int:
    step = line.step
    if line.blocked() or step <= 0 or limit <= line.allocated:
        return 0
    return (limit - line.allocated) // step


def _room_min_lot(line: AllocationLine) -> int:
    """Steps up to min_lot. Demand may be exceeded, otherwise a higher minimum is unreachable."""
    step, current = line.step, line.allocated
    if line.blocked() or step <= 0 or current >= line.min_lot:
        return 0
    return (line.min_lot - current + step - 1) // step


def _room_cover(line: AllocationLine) -> int:
    step, current = line.step, line.allocated
    if line.blocked() or step <= 0 or current >= line.demand_qty:
        return 0
    return (line.demand_qty - current + step - 1) // step


def _robin(band: list[AllocationLine], budget: int, room_of) -> int:
    rows: list[list] = []
    for line in band:
        room = room_of(line)
        if room > 0 and line.step > 0:
            rows.append([line, room, 0])
    while budget > 0 and rows:
        active = [row for row in rows if row[2] < row[1] and row[0].step <= budget]
        if not active:
            break
        cost = sum(row[0].step for row in active)
        if cost <= budget:
            rounds = min(budget // cost, min(row[1] - row[2] for row in active))
            for row in active:
                row[2] += rounds
            budget -= cost * rounds
            continue
        progressed = False
        for row in active:
            if row[0].step <= budget:
                row[2] += 1
                budget -= row[0].step
                progressed = True
        if not progressed:
            break
    for line, _room, taken in rows:
        line.allocated += taken * line.step
    return budget


def _by_priority(lines, budget: int, room_of, key) -> int:
    ordered = sorted(lines, key=key)
    for priority in sorted({line.priority for line in ordered}):
        band = [line for line in ordered if line.priority == priority]
        budget = _robin(band, budget, room_of)
    return budget


def _share_even(lines: list[AllocationLine], budget: int) -> int:
    """Base share rounded down to the step, tail from the highest request_id."""
    if budget <= 0 or not lines:
        return 0
    quota, base = budget // len(lines), 0
    for line in lines:
        share = (quota // line.step) * line.step if quota > 0 and line.step > 0 else 0
        line.allocated += share
        base += share
    leftover = budget - base
    ordered = sorted(lines, key=lambda line: line.request_id, reverse=True)
    room = lambda line, leftover=leftover: (
        leftover // line.step if 0 < line.step <= leftover else 0
    )
    return budget - _robin(ordered, leftover, room)


def _case_key(line: AllocationLine) -> tuple:
    return (line.priority, line.request_id)


def _group_key(line: AllocationLine) -> tuple:
    return (line.priority, line.case_id, line.request_id)


class Allocator:
    def __init__(
        self, requests: list[RequestCSVRow], supplies: list[SupplyCSVRow]
    ) -> None:
        self.stock: dict[str, int] = {}
        self._supplies: dict[str, SupplyCSVRow] = {}
        for supply in supplies:
            item_id = _item_id(supply)
            self.stock[item_id] = self.stock.get(item_id, 0) + supply.available_qty
            self._supplies[supply.case_id] = supply
        self.lines: list[AllocationLine] = []
        self._by_case: dict[str, list[AllocationLine]] = {}
        for request in requests:
            supply = self._supplies.get(request.case_id)
            if supply is None:
                logger.error(
                    "request %s has no supply, case %s skipped",
                    request.request_id,
                    request.case_id,
                )
                continue
            line = AllocationLine(request, supply)
            self.lines.append(line)
            self._by_case.setdefault(line.case_id, []).append(line)

    @timer
    def run(self) -> list[AllocationLine]:
        self._quotas()
        logger.info("case quotas finished")
        self._apply(_room_min_lot)
        logger.info("minimum lots finished")
        self._apply(lambda line: _room_upto(line, line.demand_qty))
        logger.info("demand fill finished")
        self._apply(_room_cover)
        logger.info("demand cover finished")
        self._share()
        logger.info("even remainder finished")
        self._release_invalid()
        logger.info("lot check finished")
        return self.lines

    def _apply(self, room_of) -> None:
        for item_id, lines in self._groups().items():
            self.stock[item_id] = _by_priority(
                lines, self.stock[item_id], room_of, _group_key
            )

    def _share(self) -> None:
        for item_id, lines in self._groups().items():
            self.stock[item_id] -= _share_even(lines, self.stock[item_id])

    def _release_invalid(self) -> None:
        """Ship 0 or a lot at least min_lot and a multiple of the step. Otherwise return the qty."""
        for line in self.lines:
            qty, step = line.allocated, line.step
            if qty == 0:
                continue
            if step <= 0 or qty % step != 0 or qty < line.min_lot:
                logger.warning(
                    "lot revoked: %s, qty %s, min_lot %s, step %s",
                    line.request_id,
                    qty,
                    line.min_lot,
                    step,
                )
                line.allocated = 0
                self.stock[line.item_id] += qty

    def _groups(self) -> dict[str, list[AllocationLine]]:
        groups: dict[str, list[AllocationLine]] = {}
        for case_id in sorted(self._supplies):
            item_id = _item_id(self._supplies[case_id])
            groups.setdefault(item_id, []).extend(self._by_case.get(case_id, []))
        return groups

    def _quotas(self) -> None:
        to_demand = lambda line: _room_upto(line, line.demand_qty)
        for case_id in sorted(self._supplies):
            lines = self._by_case.get(case_id, [])
            if not lines:
                continue
            item_id = lines[0].item_id
            budget = min(self._supplies[case_id].available_qty, self.stock[item_id])
            budget = _by_priority(lines, budget, to_demand, _case_key)
            self.stock[item_id] -= sum(line.allocated for line in lines)
