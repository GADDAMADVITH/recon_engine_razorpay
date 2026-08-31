"""Developer-only Razorpay connectivity check (not part of the HTTP API).

Usage:
    export RAZORPAY_KEY_ID=...
    export RAZORPAY_KEY_SECRET=...
    python -m integrations.razorpay.verify_connectivity
"""

from __future__ import annotations

import sys

from integrations.razorpay.client import (
    RazorpayAPIError,
    RazorpayClient,
    RazorpayCredentialsError,
    RazorpayNetworkError,
)
from integrations.razorpay.models import PaginationParams


def verify_connectivity() -> int:
    """Perform a minimal read-only call against the Razorpay API."""
    try:
        with RazorpayClient.from_env() as client:
            orders = client.fetch_orders(PaginationParams(count=1, skip=0))
    except RazorpayCredentialsError as exc:
        print(f"Razorpay connectivity check failed: {exc}", file=sys.stderr)
        return 2
    except RazorpayNetworkError as exc:
        print(f"Razorpay connectivity check failed: {exc}", file=sys.stderr)
        return 3
    except RazorpayAPIError as exc:
        print(
            f"Razorpay connectivity check failed: HTTP {exc.status_code} ({exc.error_code or 'unknown'})",
            file=sys.stderr,
        )
        return 4

    print("Razorpay connectivity check succeeded.")
    print(f"Fetched {orders.count} order record(s) from entity '{orders.entity}'.")
    return 0


def main() -> None:
    raise SystemExit(verify_connectivity())


if __name__ == "__main__":
    main()
