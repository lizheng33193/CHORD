"""Live E2E checks for the SQLite Orchestrator memory subsystem.

Start the app first:
    conda activate maps
    uvicorn app.main:app --reload

Then run:
    python scripts/memory_e2e_live.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LiveClient:
    base_url: str
    timeout: float

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=req_headers,
            method="POST",
        )
        return self._open_json(req)

    def get_json(self, path: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + path, headers=headers or {}, method="GET")
        return self._open_json(req)

    def delete_json(self, path: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url + path, headers=headers or {}, method="DELETE")
        return self._open_json(req)

    def stream(self, path: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
        req = urllib.request.Request(self.base_url + path, headers=headers or {}, method="GET")
        events: list[dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    raw_payload = line[len("data:") :].strip()
                    if not raw_payload:
                        continue
                    event = json.loads(raw_payload)
                    events.append(event)
                    if event.get("type") == "done":
                        break
        except urllib.error.URLError as exc:
            raise RuntimeError(f"SSE stream failed: {exc}") from exc
        return events

    def _open_json(self, req: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} {req.full_url}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Request failed {req.full_url}: {exc}") from exc


def _identity(user_id: str, project_id: str, country: str) -> dict[str, str]:
    return {
        "X-User-ID": user_id,
        "X-Project-ID": project_id,
        "X-Country": country,
    }


def _run_turn(client: LiveClient, message: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    created = client.post_json(
        "/api/orchestrator/sessions",
        {"initial_message": message},
        headers=headers,
    )
    session_id = created["session_id"]
    return client.stream(f"/api/orchestrator/sessions/{session_id}/stream", headers=headers)


def _final_message(events: list[dict[str, Any]]) -> str:
    for event in events:
        if event.get("type") == "final":
            return str(event.get("final_message") or "")
    return ""


def _query(
    client: LiveClient,
    *,
    query: str,
    user_id: str,
    project_id: str,
    country: str,
    category: str | None = None,
) -> list[dict[str, Any]]:
    body: dict[str, Any] = {
        "query": query,
        "user_id": user_id,
        "project_id": project_id,
        "country": country,
        "top_k": 20,
    }
    if category:
        body["category"] = category
    return client.post_json("/api/orchestrator/memory/query", body).get("results", [])


def _identity_qs(user_id: str, project_id: str, country: str) -> str:
    return urllib.parse.urlencode({
        "user_id": user_id,
        "project_id": project_id,
        "country": country,
    })


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(base_url: str, timeout: float) -> None:
    client = LiveClient(base_url.rstrip("/"), timeout)
    suffix = str(int(time.time()))
    user_id = f"memory-e2e-user-{suffix}"
    other_user_id = f"memory-e2e-other-{suffix}"
    project_id = f"memory-e2e-project-{suffix}"

    status = client.get_json("/api/orchestrator/memory/status")
    _assert("db_path" in status and isinstance(status.get("total"), int), "memory status is not explainable")
    print(f"[ok] memory status db={status['db_path']} total={status['total']}")

    headers = _identity(user_id, project_id, "mx")
    noise_events = _run_turn(client, "你好，你是什么模型？", headers)
    print(f"[info] noise final: {_final_message(noise_events)[:120]}")
    noise_results = _query(
        client,
        query="",
        user_id=user_id,
        project_id=project_id,
        country="mx",
    )
    _assert(noise_results == [], "noise/model-identity chat should not write long-term memory")
    print("[ok] noise did not write memory")

    preference_events = _run_turn(
        client,
        "请记住：我偏好中文输出，并且回答要简洁。",
        headers,
    )
    print(f"[info] preference final: {_final_message(preference_events)[:120]}")
    preference_results = _query(
        client,
        query="中文输出 简洁",
        user_id=user_id,
        project_id=project_id,
        country="mx",
        category="preference",
    )
    _assert(
        any("中文输出" in str(item.get("content", "")) for item in preference_results),
        "explicit preference was not persisted",
    )
    _assert("score_parts" in preference_results[0], "query result should include score_parts")
    print("[ok] explicit preference persisted and query is explainable")

    recall_events = _run_turn(client, "请只根据你检索到的长期记忆回答：我之前让你记住的输出偏好是什么？", headers)
    recall_final = _final_message(recall_events)
    print(f"[info] cross-session recall final: {recall_final[:180]}")
    _assert(recall_final, "cross-session recall session did not produce a final message")
    _assert(
        ("中文" in recall_final or "简洁" in recall_final),
        "cross-session recall final did not mention the persisted preference",
    )

    other_user_results = _query(
        client,
        query="中文输出 简洁",
        user_id=other_user_id,
        project_id=project_id,
        country="mx",
    )
    _assert(other_user_results == [], "other user should not retrieve this user's memory")
    print("[ok] user isolation")

    other_country_results = _query(
        client,
        query="中文输出 简洁",
        user_id=user_id,
        project_id=project_id,
        country="th",
    )
    _assert(other_country_results == [], "other country should not retrieve mx memory")
    print("[ok] country isolation")

    managed = client.post_json(
        "/api/orchestrator/memory",
        {
            "user_id": user_id,
            "project_id": project_id,
            "country": "mx",
            "content": "请记住：我偏好英文输出",
            "category": "preference",
        },
    ).get("memory", {})
    memory_id = managed.get("memory_id")
    _assert(memory_id, "memory management create did not return memory_id")
    _assert(
        any(item.get("memory_id") == memory_id for item in _query(
            client,
            query="英文输出",
            user_id=user_id,
            project_id=project_id,
            country="mx",
        )),
        "managed memory was not queryable after create",
    )
    qs = _identity_qs(user_id, project_id, "mx")
    archived = client.post_json(f"/api/orchestrator/memory/{memory_id}/archive?{qs}", {})
    _assert(archived.get("memory", {}).get("status") == "archived", "managed memory did not archive")
    _assert(
        not any(item.get("memory_id") == memory_id for item in _query(
            client,
            query="英文输出",
            user_id=user_id,
            project_id=project_id,
            country="mx",
        )),
        "archived memory should not appear in active query",
    )
    restored = client.post_json(f"/api/orchestrator/memory/{memory_id}/restore?{qs}", {})
    _assert(restored.get("memory", {}).get("status") == "active", "managed memory did not restore")
    deleted = client.delete_json(f"/api/orchestrator/memory/{memory_id}?{qs}")
    _assert(deleted.get("memory", {}).get("status") == "deleted", "managed memory did not soft delete")
    print("[ok] memory management create/archive/restore/delete")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    try:
        run(args.base_url, args.timeout)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[failed] {exc}", file=sys.stderr)
        return 1
    print("[ok] live memory e2e passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
