import csv
from io import StringIO
from logging import getLogger
from pathlib import Path

from app.allocation import AllocationLine, Allocator, _item_id
from app.schemas import RequestCSVRow, SupplyCSVRow
from app.utils import timer

logger = getLogger(__name__)


class AllocateReportBuilder:
    def __init__(
        self,
        requests: list[RequestCSVRow],
        supplies: list[SupplyCSVRow],
    ) -> None:
        self.requests = requests
        self.supplies = supplies

    def build(self) -> str:
        allocator = Allocator(self.requests, self.supplies)
        lines = allocator.run()
        return self._render(lines) + self._render_remainder(allocator)

    @timer
    def write(self, path: str) -> str:
        text = self.build()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        logger.info("report written: %s", path)
        return text

    def _render(self, lines: list[AllocationLine]) -> str:
        ordered = sorted(lines, key=lambda line: (line.case_id, line.request_id))
        buffer = StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["case_id", "request_id", "dest_location", "allocated"])
        for line in ordered:
            writer.writerow(
                [
                    line.case_id,
                    line.request_id,
                    line.dest_location,
                    line.allocated,
                ]
            )
        return buffer.getvalue()

    def _render_remainder(self, allocator: Allocator) -> str:
        pools: dict[str, tuple[str, str]] = {}
        for supply in self.supplies:
            pools[_item_id(supply)] = (supply.item, supply.source_location)
        buffer = StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["item", "source_location", "unallocated"])
        ordered = sorted(pools.items(), key=lambda row: row[1])
        for item_id, (item, source) in ordered:
            writer.writerow([item, source, allocator.stock.get(item_id, 0)])
        return "\n" + buffer.getvalue()
