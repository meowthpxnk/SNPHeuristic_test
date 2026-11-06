import datetime

from pydantic import field_validator

from app.utils import CSVRow


class RequestCSVRow(CSVRow):
    case_id: str
    request_id: str
    dest_location: str
    priority: int
    demand_qty: int
    min_lot: int
    rounding_value: int

    @field_validator(
        "priority",
        "demand_qty",
        "min_lot",
        "rounding_value",
        mode="before",
    )
    @classmethod
    def validate_positive(cls, value: int) -> int:
        return abs(int(value))


class SupplyCSVRow(CSVRow):
    case_id: str
    period: datetime.datetime
    item: str
    source_location: str
    available_qty: int

    @field_validator("period", mode="before")
    @classmethod
    def validate_period(cls, value: str) -> datetime.datetime:
        return datetime.datetime.strptime(value, "%Y-%m")

    @field_validator("available_qty", mode="before")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        return abs(int(value))
