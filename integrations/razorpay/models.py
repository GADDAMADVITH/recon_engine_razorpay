"""Typed models for Razorpay API integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PaginationParams:
    """Standard Razorpay list pagination parameters."""

    count: int = 10
    skip: int = 0
    from_ts: int | None = None
    to_ts: int | None = None

    def validate(self) -> None:
        if self.count < 1 or self.count > 100:
            raise ValueError("count must be between 1 and 100")
        if self.skip < 0:
            raise ValueError("skip must be >= 0")

    def to_query_params(self) -> dict[str, int]:
        self.validate()
        params: dict[str, int] = {"count": self.count, "skip": self.skip}
        if self.from_ts is not None:
            params["from"] = self.from_ts
        if self.to_ts is not None:
            params["to"] = self.to_ts
        return params


@dataclass(frozen=True)
class ReconPaginationParams:
    """Pagination for settlement reconciliation (allows count up to 1000)."""

    count: int = 100
    skip: int = 0

    def validate(self) -> None:
        if self.count < 1 or self.count > 1000:
            raise ValueError("count must be between 1 and 1000")
        if self.skip < 0:
            raise ValueError("skip must be >= 0")

    def to_query_params(self) -> dict[str, int]:
        self.validate()
        return {"count": self.count, "skip": self.skip}


@dataclass(frozen=True)
class PaginatedList(Generic[T]):
    """Structured wrapper for Razorpay collection responses."""

    entity: str
    count: int
    items: list[T] = field(default_factory=list)

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> PaginatedList[dict[str, Any]]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("Razorpay response missing 'items' list")
        count = payload.get("count")
        if not isinstance(count, int):
            raise ValueError("Razorpay response missing integer 'count'")
        entity = payload.get("entity")
        if not isinstance(entity, str):
            raise ValueError("Razorpay response missing 'entity'")
        return cls(entity=entity, count=count, items=items)


@dataclass(frozen=True)
class SettlementReconParams:
    """Query parameters for GET /settlements/recon/combined."""

    year: int
    month: int
    day: int | None = None
    pagination: ReconPaginationParams = field(default_factory=ReconPaginationParams)

    def validate(self) -> None:
        if self.year < 2000 or self.year > 2100:
            raise ValueError("year must be a four-digit calendar year")
        if self.month < 1 or self.month > 12:
            raise ValueError("month must be between 1 and 12")
        if self.day is not None and (self.day < 1 or self.day > 31):
            raise ValueError("day must be between 1 and 31")
        self.pagination.validate()

    def to_query_params(self) -> dict[str, int]:
        self.validate()
        params = {
            "year": self.year,
            "month": self.month,
            **self.pagination.to_query_params(),
        }
        if self.day is not None:
            params["day"] = self.day
        return params
