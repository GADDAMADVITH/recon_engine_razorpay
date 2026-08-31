"""Read-only Razorpay REST API client."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from integrations.razorpay.models import (
    PaginatedList,
    PaginationParams,
    ReconPaginationParams,
    SettlementReconParams,
)

DEFAULT_BASE_URL = "https://api.razorpay.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
_SECRET_PATTERN = re.compile(r"(key_secret|api_secret|password)\s*[=:]\s*\S+", re.I)


class RazorpayCredentialsError(ValueError):
    """Raised when required Razorpay credentials are missing or invalid."""


class RazorpayNetworkError(RuntimeError):
    """Raised when the HTTP transport fails before a response is received."""


class RazorpayAPIError(RuntimeError):
    """Raised when Razorpay returns a non-success HTTP status."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
        description: str | None = None,
    ) -> None:
        safe_message = _sanitize_message(message)
        super().__init__(safe_message)
        self.status_code = status_code
        self.error_code = error_code
        self.description = _sanitize_message(description) if description else None


@dataclass(frozen=True)
class RazorpayConfig:
    """Environment-backed Razorpay client configuration."""

    key_id: str
    key_secret: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not self.key_id.strip():
            raise RazorpayCredentialsError("RAZORPAY_KEY_ID is required")
        if not self.key_secret.strip():
            raise RazorpayCredentialsError("RAZORPAY_KEY_SECRET is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    @classmethod
    def from_env(
        cls,
        *,
        key_id: str | None = None,
        key_secret: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> RazorpayConfig:
        resolved_key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "")
        resolved_key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "")
        if not resolved_key_id or not resolved_key_secret:
            raise RazorpayCredentialsError(
                "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in the environment"
            )
        return cls(
            key_id=resolved_key_id.strip(),
            key_secret=resolved_key_secret.strip(),
            base_url=(base_url or os.environ.get("RAZORPAY_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            timeout_seconds=timeout_seconds
            if timeout_seconds is not None
            else float(os.environ.get("RAZORPAY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        )


def _sanitize_message(message: str | None) -> str:
    if not message:
        return ""
    return _SECRET_PATTERN.sub("[REDACTED]", message)


class RazorpayClient:
    """Read-only Razorpay API client using HTTP Basic authentication."""

    def __init__(
        self,
        config: RazorpayConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(
            base_url=config.base_url,
            auth=(config.key_id, config.key_secret),
            timeout=httpx.Timeout(config.timeout_seconds),
            headers={"Accept": "application/json"},
        )

    @classmethod
    def from_env(cls, **kwargs: Any) -> RazorpayClient:
        return cls(RazorpayConfig.from_env(**kwargs))

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> RazorpayClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def fetch_orders(self, pagination: PaginationParams | None = None) -> PaginatedList[dict[str, Any]]:
        return self._fetch_collection("/orders", pagination or PaginationParams())

    def fetch_order(self, order_id: str) -> dict[str, Any]:
        return self._fetch_entity(f"/orders/{order_id}")

    def iter_orders(
        self,
        *,
        page_size: int = 100,
        from_ts: int | None = None,
        to_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_collection(
            "/orders",
            page_size=page_size,
            from_ts=from_ts,
            to_ts=to_ts,
            max_pages=max_pages,
        )

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------

    def fetch_payments(self, pagination: PaginationParams | None = None) -> PaginatedList[dict[str, Any]]:
        return self._fetch_collection("/payments", pagination or PaginationParams())

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self._fetch_entity(f"/payments/{payment_id}")

    def iter_payments(
        self,
        *,
        page_size: int = 100,
        from_ts: int | None = None,
        to_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_collection(
            "/payments",
            page_size=page_size,
            from_ts=from_ts,
            to_ts=to_ts,
            max_pages=max_pages,
        )

    # ------------------------------------------------------------------
    # Refunds
    # ------------------------------------------------------------------

    def fetch_refunds(self, pagination: PaginationParams | None = None) -> PaginatedList[dict[str, Any]]:
        return self._fetch_collection("/refunds", pagination or PaginationParams())

    def fetch_refund(self, refund_id: str) -> dict[str, Any]:
        return self._fetch_entity(f"/refunds/{refund_id}")

    def iter_refunds(
        self,
        *,
        page_size: int = 100,
        from_ts: int | None = None,
        to_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_collection(
            "/refunds",
            page_size=page_size,
            from_ts=from_ts,
            to_ts=to_ts,
            max_pages=max_pages,
        )

    # ------------------------------------------------------------------
    # Settlements
    # ------------------------------------------------------------------

    def fetch_settlements(self, pagination: PaginationParams | None = None) -> PaginatedList[dict[str, Any]]:
        return self._fetch_collection("/settlements", pagination or PaginationParams())

    def fetch_settlement(self, settlement_id: str) -> dict[str, Any]:
        return self._fetch_entity(f"/settlements/{settlement_id}")

    def fetch_settlement_recon(
        self,
        params: SettlementReconParams,
    ) -> PaginatedList[dict[str, Any]]:
        query = params.to_query_params()
        payload = self._request("GET", "/settlements/recon/combined", params=query)
        return PaginatedList.from_response(payload)

    def iter_settlements(
        self,
        *,
        page_size: int = 100,
        from_ts: int | None = None,
        to_ts: int | None = None,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_collection(
            "/settlements",
            page_size=page_size,
            from_ts=from_ts,
            to_ts=to_ts,
            max_pages=max_pages,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_collection(
        self,
        path: str,
        pagination: PaginationParams,
    ) -> PaginatedList[dict[str, Any]]:
        payload = self._request("GET", path, params=pagination.to_query_params())
        return PaginatedList.from_response(payload)

    def _fetch_entity(self, path: str) -> dict[str, Any]:
        payload = self._request("GET", path)
        if not isinstance(payload, dict):
            raise RazorpayAPIError(
                "Unexpected Razorpay entity response",
                status_code=200,
            )
        return payload

    def _iter_collection(
        self,
        path: str,
        *,
        page_size: int,
        from_ts: int | None,
        to_ts: int | None,
        max_pages: int | None,
    ) -> Iterator[dict[str, Any]]:
        skip = 0
        pages = 0
        while True:
            page = self._fetch_collection(
                path,
                PaginationParams(count=page_size, skip=skip, from_ts=from_ts, to_ts=to_ts),
            )
            if not page.items:
                break
            for item in page.items:
                yield item
            if len(page.items) < page_size:
                break
            skip += page_size
            pages += 1
            if max_pages is not None and pages >= max_pages:
                break

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, params=params)
        except httpx.TimeoutException as exc:
            raise RazorpayNetworkError("Razorpay request timed out") from exc
        except httpx.RequestError as exc:
            message = _sanitize_message(str(exc))
            raise RazorpayNetworkError(f"Razorpay request failed: {message}") from exc

        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        payload: dict[str, Any] | None = None
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    payload = parsed
            except ValueError:
                payload = None

        if response.is_success:
            if payload is None:
                raise RazorpayAPIError(
                    "Razorpay returned a non-JSON success response",
                    status_code=response.status_code,
                )
            return payload

        error_code: str | None = None
        description: str | None = None
        if payload and isinstance(payload.get("error"), dict):
            error_body = payload["error"]
            error_code = error_body.get("code")
            description = error_body.get("description")

        message = description or f"Razorpay API request failed with status {response.status_code}"
        raise RazorpayAPIError(
            message,
            status_code=response.status_code,
            error_code=error_code if isinstance(error_code, str) else None,
            description=description if isinstance(description, str) else None,
        )
