from logging import getLogger

import app.core  # noqa: F401  # configure logging
from app.report import AllocateReportBuilder
from app.schemas import RequestCSVRow, SupplyCSVRow

logger = getLogger("app")


def main() -> None:
    requests = RequestCSVRow.read("data/requests.csv")
    logger.info("requests loaded: %s", len(requests))
    supplies = SupplyCSVRow.read("data/supply.csv")
    logger.info("supplies loaded: %s", len(supplies))
    report = AllocateReportBuilder(requests, supplies)
    text = report.write("output/shipments.csv")
    print(text)
    logger.info("allocation finished")


if __name__ == "__main__":
    main()
