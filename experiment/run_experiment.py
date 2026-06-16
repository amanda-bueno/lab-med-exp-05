from __future__ import annotations

import csv
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from experiment.config import BASE_URL, DELAY_SECONDS, LIMIT, PAGE, RAW_RESULTS, REPETITIONS, USER_ID, WARMUP
from experiment.scenarios import Scenario, build_scenarios


FIELDNAMES = [
    "timestamp",
    "scenario",
    "treatment",
    "repetition",
    "execution_order",
    "response_time_ms",
    "response_size_bytes",
    "status_code",
    "success",
    "records_returned",
    "error",
]


@dataclass
class Measurement:
    response_time_ms: float
    response_size_bytes: int
    status_code: int
    success: bool
    records_returned: int
    error: str = ""


def _request(method: str, url: str, body: bytes | None = None) -> tuple[int, bytes, float]:
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read()
            elapsed = (time.perf_counter() - start) * 1000.0
            return response.status, data, elapsed
    except HTTPError as exc:
        data = exc.read()
        elapsed = (time.perf_counter() - start) * 1000.0
        return exc.code, data, elapsed


def _count_records(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value) + sum(_count_records(item) for item in value)
    if isinstance(value, dict):
        nested = sum(_count_records(item) for item in value.values())
        return 1 + nested
    return 0


def execute_graphql(scenario: Scenario) -> Measurement:
    try:
        payload = json.dumps({"query": scenario.graphql_query}).encode("utf-8")
        status, body, elapsed = _request("POST", f"{BASE_URL}/graphql", payload)
        parsed = json.loads(body.decode("utf-8"))
        success = status == 200 and "errors" not in parsed
        data = parsed.get("data", {})
        root_value = next(iter(data.values())) if isinstance(data, dict) and data else data
        records = _count_records(root_value)
        return Measurement(elapsed, len(body), status, success, records, "" if success else str(parsed.get("errors")))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return Measurement(0.0, 0, 0, False, 0, str(exc))


def execute_rest(scenario: Scenario) -> Measurement:
    try:
        start = time.perf_counter()
        total_size = 0
        statuses: list[int] = []
        records = 0

        if scenario.name == "simple_user":
            status, body, _ = _request("GET", f"{BASE_URL}/users/{USER_ID}")
            statuses.append(status)
            total_size += len(body)
            records += _count_records(json.loads(body.decode("utf-8")).get("data"))

        elif scenario.name == "user_list":
            status, body, _ = _request("GET", f"{BASE_URL}/users?page={PAGE}&limit={LIMIT}")
            statuses.append(status)
            total_size += len(body)
            records += _count_records(json.loads(body.decode("utf-8")).get("data"))

        elif scenario.name in {"nested_data", "post_titles", "full_profile"}:
            if scenario.name != "post_titles":
                status, user_body, _ = _request("GET", f"{BASE_URL}/users/{USER_ID}")
                statuses.append(status)
                total_size += len(user_body)
                user_payload = json.loads(user_body.decode("utf-8"))
                records += _count_records(user_payload.get("data"))

            status, posts_body, _ = _request("GET", f"{BASE_URL}/users/{USER_ID}/posts")
            statuses.append(status)
            total_size += len(posts_body)
            posts_payload = json.loads(posts_body.decode("utf-8"))
            posts = posts_payload.get("data", [])
            records += _count_records(posts)

            if scenario.name != "post_titles":
                for post in posts:
                    status, comments_body, _ = _request("GET", f"{BASE_URL}/posts/{post['id']}/comments")
                    statuses.append(status)
                    total_size += len(comments_body)
                    records += _count_records(json.loads(comments_body.decode("utf-8")).get("data"))

        else:
            return Measurement(0.0, 0, 0, False, 0, f"unsupported scenario {scenario.name}")

        elapsed = (time.perf_counter() - start) * 1000.0
        success = all(status == 200 for status in statuses)
        status_code = 200 if success else max(statuses)
        return Measurement(elapsed, total_size, status_code, success, records)
    except (OSError, URLError, json.JSONDecodeError, KeyError) as exc:
        return Measurement(0.0, 0, 0, False, 0, str(exc))


def execute_scenario(scenario: Scenario, treatment: str) -> Measurement:
    if treatment == "REST":
        return execute_rest(scenario)
    if treatment == "GRAPHQL":
        return execute_graphql(scenario)
    raise ValueError(f"unsupported treatment {treatment}")


def run_warmup(scenario: Scenario) -> None:
    for _ in range(WARMUP):
        treatments = ["REST", "GRAPHQL"]
        random.shuffle(treatments)
        for treatment in treatments:
            execute_scenario(scenario, treatment)
            time.sleep(DELAY_SECONDS)


def write_row(writer: csv.DictWriter, scenario: Scenario, treatment: str, repetition: int, order: int, result: Measurement) -> None:
    writer.writerow(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario": scenario.name,
            "treatment": treatment,
            "repetition": repetition,
            "execution_order": order,
            "response_time_ms": f"{result.response_time_ms:.4f}",
            "response_size_bytes": result.response_size_bytes,
            "status_code": result.status_code,
            "success": str(result.success).lower(),
            "records_returned": result.records_returned,
            "error": result.error,
        }
    )


def run(output_path: Path = RAW_RESULTS) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenarios = build_scenarios(USER_ID, PAGE, LIMIT)

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()

        for scenario in scenarios:
            print(f"Warmup: {scenario.name}")
            run_warmup(scenario)
            for repetition in range(1, REPETITIONS + 1):
                treatments = ["REST", "GRAPHQL"]
                random.shuffle(treatments)
                for order, treatment in enumerate(treatments, start=1):
                    result = execute_scenario(scenario, treatment)
                    write_row(writer, scenario, treatment, repetition, order, result)
                    file.flush()
                    time.sleep(DELAY_SECONDS)

    print(f"Results written to {output_path}")


if __name__ == "__main__":
    run()
