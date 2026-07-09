from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from urllib import error as urllib_error
from urllib import request as urllib_request


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _http_status(url: str, timeout: float) -> tuple[int, str]:
    with urllib_request.urlopen(url, timeout=timeout) as response:
        body = response.read(200).decode("utf-8", errors="replace")
        return response.status, body


def _wait_for_health(base_url: str, timeout_seconds: int) -> CheckResult:
    deadline = time.time() + timeout_seconds
    last_error = "timeout"
    url = f"{base_url.rstrip('/')}/health"
    while time.time() < deadline:
        try:
            status, body = _http_status(url, timeout=5)
            if status == 200:
                return CheckResult("health", True, f"200 {body.strip()}")
            last_error = f"unexpected status {status}"
        except urllib_error.HTTPError as exc:
            last_error = f"http {exc.code}"
        except urllib_error.URLError as exc:
            last_error = str(exc.reason)
        time.sleep(1)
    return CheckResult("health", False, last_error)


def _check_docs(base_url: str) -> CheckResult:
    url = f"{base_url.rstrip('/')}/docs"
    try:
        status, _ = _http_status(url, timeout=5)
        if status == 200:
            return CheckResult("docs", True, "200")
        return CheckResult("docs", False, f"unexpected status {status}")
    except urllib_error.HTTPError as exc:
        if exc.code >= 500:
            return CheckResult("docs", False, f"http {exc.code}")
        return CheckResult("docs", True, f"advisory http {exc.code}")
    except urllib_error.URLError as exc:
        return CheckResult("docs", False, str(exc.reason))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a minimal startup smoke check.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    results = [
        _wait_for_health(args.base_url, args.timeout_seconds),
        _check_docs(args.base_url),
    ]
    for result in results:
        print(f"{result.name}: {'ok' if result.ok else 'fail'} - {result.detail}")

    failed = [result for result in results if not result.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
