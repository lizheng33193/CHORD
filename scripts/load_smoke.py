from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class RequestResult:
    path: str
    ok: bool
    status_code: int | None
    latency_ms: float
    error: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimum safe GET-only load smoke for CHORD.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/load_smoke"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--include-docs", action="store_true")
    return parser.parse_args()


def _resolve_path(path: Path, *, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _validate_args(args: argparse.Namespace) -> tuple[bool, str | None, int]:
    if args.requests < 1:
        return False, "--requests must be greater than or equal to 1", 2
    if args.concurrency < 1:
        return False, "--concurrency must be greater than or equal to 1", 2
    if args.timeout_seconds <= 0:
        return False, "--timeout-seconds must be greater than 0", 2
    return True, None, 0


def _fetch_once(base_url: str, path: str, timeout_seconds: int) -> RequestResult:
    start = time.perf_counter()
    url = f"{base_url.rstrip('/')}{path}"
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response.read(128)
            latency_ms = round((time.perf_counter() - start) * 1000, 3)
            ok = 200 <= response.status < 300
            return RequestResult(path=path, ok=ok, status_code=response.status, latency_ms=latency_ms)
    except error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        return RequestResult(
            path=path,
            ok=False,
            status_code=exc.code,
            latency_ms=latency_ms,
            error=f"http {exc.code}",
        )
    except Exception as exc:  # pragma: no cover - exercised in runtime smoke
        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        return RequestResult(
            path=path,
            ok=False,
            status_code=None,
            latency_ms=latency_ms,
            error=str(exc),
        )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 3)


def _latency_summary(latencies: list[float]) -> dict[str, float]:
    if not latencies:
        return {"min": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "min": round(min(latencies), 3),
        "avg": round(sum(latencies) / len(latencies), 3),
        "p50": _percentile(latencies, 0.50),
        "p95": _percentile(latencies, 0.95),
        "max": round(max(latencies), 3),
    }


def _run_endpoint(
    *,
    base_url: str,
    path: str,
    request_count: int,
    concurrency: int,
    timeout_seconds: int,
    required: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(_fetch_once, base_url, path, timeout_seconds)
            for _ in range(request_count)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    success_count = sum(1 for item in results if item.ok)
    failure_count = request_count - success_count
    status_5xx_count = sum(1 for item in results if item.status_code is not None and item.status_code >= 500)
    latencies = [item.latency_ms for item in results]
    error_rate = round(failure_count / request_count, 6)
    latency_ms = _latency_summary(latencies)

    if path == "/health":
        if status_5xx_count > 0:
            failures.append("/health returned one or more 5xx responses during load smoke")
        if error_rate > 0.01:
            failures.append(f"/health error_rate exceeded threshold: {error_rate}")
        if latency_ms["p95"] > 1000:
            warnings.append(f"/health p95 latency exceeded warning threshold: {latency_ms['p95']}ms")
    else:
        if status_5xx_count > 0:
            failures.append(f"{path} returned one or more 5xx responses during advisory load smoke")
        elif failure_count > 0:
            warnings.append(f"{path} returned one or more non-2xx responses during advisory load smoke")
        if latency_ms["p95"] > 1000:
            warnings.append(f"{path} p95 latency exceeded warning threshold: {latency_ms['p95']}ms")

    endpoint_payload = {
        "path": path,
        "required": required,
        "total_requests": request_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "status_5xx_count": status_5xx_count,
        "error_rate": error_rate,
        "latency_ms": latency_ms,
    }
    sample_errors = [item.error for item in results if item.error][:5]
    if sample_errors:
        endpoint_payload["sample_errors"] = sample_errors
    sample_status_codes = [item.status_code for item in results if item.status_code is not None][:10]
    if sample_status_codes:
        endpoint_payload["sample_status_codes"] = sample_status_codes
    return endpoint_payload, warnings, failures


def _resolve_report_path(output_dir: Path) -> Path:
    stem = datetime.now(UTC).strftime("load-smoke-%Y%m%d-%H%M%S")
    candidate = output_dir / f"{stem}.json"
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        candidate = output_dir / f"{stem}-{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def main() -> int:
    args = _parse_args()
    valid, error_message, exit_code = _validate_args(args)
    if not valid:
        print(f"error: {error_message}", file=sys.stderr)
        return exit_code

    project_root = args.project_root.resolve()
    effective_concurrency = min(args.concurrency, args.requests)
    endpoints = [("/health", True)]
    if args.include_docs:
        endpoints.append(("/docs", False))

    payload_endpoints: list[dict[str, Any]] = []
    warnings: list[str] = []
    failures: list[str] = []
    for path, required in endpoints:
        endpoint_payload, endpoint_warnings, endpoint_failures = _run_endpoint(
            base_url=args.base_url,
            path=path,
            request_count=args.requests,
            concurrency=effective_concurrency,
            timeout_seconds=args.timeout_seconds,
            required=required,
        )
        payload_endpoints.append(endpoint_payload)
        warnings.extend(endpoint_warnings)
        failures.extend(endpoint_failures)

    overall_status = "fail" if failures else "warn" if warnings else "pass"
    payload: dict[str, Any] = {
        "report_version": "m7d-load-smoke-v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "base_url": args.base_url,
        "requests": args.requests,
        "concurrency": effective_concurrency,
        "overall_status": overall_status,
        "go": not failures,
        "endpoints": payload_endpoints,
        "warnings": warnings,
        "failures": failures,
        "thresholds": {
            "max_error_rate": 0.01,
            "no_5xx_required": True,
            "p95_warning_ms": 1000,
        },
    }

    if args.no_write:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        output_dir = _resolve_path(args.output_dir, project_root=project_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = _resolve_report_path(output_dir)
        payload["report_path"] = str(report_path)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report: {report_path}")
        print(f"overall_status: {overall_status}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
