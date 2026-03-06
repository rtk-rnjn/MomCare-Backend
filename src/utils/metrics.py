from __future__ import annotations

import inspect
import time
from typing import Any, Dict

import orjson
from redis.asyncio import Redis


def normalize_duration(duration_sec: int) -> int:
    if duration_sec < 60:
        return 60
    if duration_sec > 3600:
        return 3600
    return duration_sec


def _decode_text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, (bytes, bytearray)) else str(value)


async def collect_runtime_metrics(redis_client: Redis, duration_sec: int) -> Dict[str, Any]:
    duration_sec = normalize_duration(duration_sec)

    requests_per_second = 0.0
    current_second_rps = 0
    total_requests = 0
    total_404 = 0
    total_500 = 0
    total_5xx = 0
    endpoint_failures = []
    endpoint_traffic = []

    now_second = int(time.time())
    rps_keys = [f"metrics:requests:sec:{ts}" for ts in range(now_second - duration_sec + 1, now_second + 1)]
    rps_values = await redis_client.mget(rps_keys)
    rps_series = [int(value or 0) for value in rps_values]

    requests_in_window = sum(rps_series)
    requests_per_second = round(requests_in_window / duration_sec, 2)
    current_second_rps = rps_series[-1] if rps_series else 0

    total_requests = int(await redis_client.get("metrics:requests:total") or 0)
    total_404 = int(await redis_client.get("metrics:status:404") or 0)
    total_500 = int(await redis_client.get("metrics:status:500") or 0)
    total_5xx = int(await redis_client.get("metrics:status:5xx") or 0)

    endpoint_failure_counts = redis_client.hgetall("metrics:endpoint_failures")
    endpoint_last_errors = redis_client.hgetall("metrics:endpoint_last_error")

    if inspect.isawaitable(endpoint_failure_counts):
        endpoint_failure_counts = await endpoint_failure_counts

    if inspect.isawaitable(endpoint_last_errors):
        endpoint_last_errors = await endpoint_last_errors

    sorted_failures = sorted(
        endpoint_failure_counts.items(),
        key=lambda item: int(item[1]),
        reverse=True,
    )[:20]

    for endpoint, count in sorted_failures:
        endpoint_name = _decode_text(endpoint)
        last_error_raw = endpoint_last_errors.get(endpoint) or endpoint_last_errors.get(endpoint_name)
        last_error = None
        if last_error_raw:
            try:
                last_error = orjson.loads(last_error_raw if isinstance(last_error_raw, bytes) else str(last_error_raw).encode("utf-8"))
            except Exception:
                last_error = {"message": _decode_text(last_error_raw)}

        endpoint_failures.append({"endpoint": endpoint_name, "count": int(count), "last_error": last_error})

    sec_keys = [f"metrics:endpoint_status:sec:{ts}" for ts in range(now_second - duration_sec + 1, now_second + 1)]
    pipe = redis_client.pipeline()
    for sec_key in sec_keys:
        pipe.hgetall(sec_key)
    sec_hashes = await pipe.execute()

    endpoint_breakdown: dict[str, dict[str, int]] = {}
    for sec_hash in sec_hashes:
        for endpoint_status_key, raw_count in sec_hash.items():
            key_text = _decode_text(endpoint_status_key)
            if "|" not in key_text:
                continue

            endpoint_name, status_text = key_text.rsplit("|", 1)
            try:
                status_code = int(status_text)
                count = int(raw_count)
            except Exception:
                continue

            if endpoint_name not in endpoint_breakdown:
                endpoint_breakdown[endpoint_name] = {"count": 0, "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}

            endpoint_breakdown[endpoint_name]["count"] += count
            if 200 <= status_code < 300:
                endpoint_breakdown[endpoint_name]["2xx"] += count
            elif 300 <= status_code < 400:
                endpoint_breakdown[endpoint_name]["3xx"] += count
            elif 400 <= status_code < 500:
                endpoint_breakdown[endpoint_name]["4xx"] += count
            elif 500 <= status_code < 600:
                endpoint_breakdown[endpoint_name]["5xx"] += count

    def parse_last_error(endpoint_name: str, endpoint_last_errors: dict):
        raw = endpoint_last_errors.get(endpoint_name) or endpoint_last_errors.get(endpoint_name.encode("utf-8"))
        if not raw:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return orjson.loads(raw)
        return orjson.loads(str(raw).encode("utf-8"))

    for endpoint_name, values in endpoint_breakdown.items():
        endpoint_traffic.append(
            {
                "endpoint": endpoint_name,
                "count": values["count"],
                "2xx": values["2xx"],
                "3xx": values["3xx"],
                "4xx": values["4xx"],
                "5xx": values["5xx"],
                "last_error": parse_last_error(endpoint_name, endpoint_last_errors),
            }
        )

    endpoint_traffic = sorted(
        endpoint_traffic,
        key=lambda item: item["count"],
        reverse=True,
    )[:30]

    return {
        "duration_sec": duration_sec,
        "requests_per_second": requests_per_second,
        "current_second_rps": current_second_rps,
        "total_requests": total_requests,
        "total_404": total_404,
        "total_500": total_500,
        "total_5xx": total_5xx,
        "endpoint_failures": endpoint_failures,
        "endpoint_traffic": endpoint_traffic,
    }
