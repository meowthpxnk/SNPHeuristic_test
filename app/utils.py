import csv
import time
from collections.abc import Callable
from functools import wraps
from logging import getLogger
from typing import Self

import yaml
from pydantic import BaseModel

# --> Timers


def timer[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    log = getLogger(func.__module__)

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        except Exception:
            log.exception("%s failed", func.__qualname__)
            raise
        finally:
            elapsed = time.perf_counter() - start
            log.debug("%s: %.4fs", func.__qualname__, elapsed)

    return wrapper


# --> YAML reading


def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as file:
        return file.read()


def read_yaml(path: str) -> dict:
    return yaml.safe_load(read_file(path))


# --> CSV reading


def read_csv(path: str, model: BaseModel) -> list[dict]:
    with open(path, encoding="utf-8") as file:
        reader = csv.DictReader(file)
        data = list(reader)
        data = [model.model_validate(row) for row in data]
        return data


class CSVRow(BaseModel):
    @classmethod
    @timer
    def read(cls, path: str) -> list[Self]:
        return read_csv(path, cls)
