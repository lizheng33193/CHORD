"""CLI entrypoint for M6A shadow vector tooling."""

from __future__ import annotations

import argparse
import json

from app.services.orchestrator_agent.memory_vector.shadow_search import (
    shadow_search_memory,
)
from app.services.orchestrator_agent.memory_vector.sync import (
    build_default_memory_vector_sync_service,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-vector")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    sync_parser = subparsers.add_parser("sync-all")
    sync_parser.add_argument("--user-id")
    sync_parser.add_argument("--project-id")
    sync_parser.add_argument("--country")
    sync_parser.add_argument("--limit", type=int)
    rebuild_parser = subparsers.add_parser("rebuild")
    rebuild_parser.add_argument("--user-id")
    rebuild_parser.add_argument("--project-id")
    rebuild_parser.add_argument("--country")
    search_parser = subparsers.add_parser("shadow-search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--user-id", required=True)
    search_parser.add_argument("--project-id")
    search_parser.add_argument("--country")
    search_parser.add_argument("--top-k", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI wrapper
    parser = build_parser()
    args = parser.parse_args(argv)
    service = build_default_memory_vector_sync_service()

    if args.command == "status":
        payload = {
            "vector_store": service.vector_store.health_check(),
            "sync_states": [
                state.__dict__
                for state in service.relational_store.list_vector_sync_states(
                    vector_namespace=service.vector_store.manifest.namespace,
                )
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync-all":
        report = service.sync_all_active(
            user_id=args.user_id,
            project_id=args.project_id,
            country=args.country,
            limit=args.limit,
        )
        print(json.dumps(report.__dict__ | {"results": [item.__dict__ for item in report.results]}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "rebuild":
        report = service.rebuild_index(
            {
                "user_id": args.user_id,
                "project_id": args.project_id,
                "country": args.country,
            }
        )
        print(json.dumps(report.__dict__ | {"results": [item.__dict__ for item in report.results]}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "shadow-search":
        result = shadow_search_memory(
            args.query,
            user_id=args.user_id,
            project_id=args.project_id,
            country=args.country,
            top_k=args.top_k,
            relational_store=service.relational_store,
            vector_store=service.vector_store,
            embedding_provider=service.embedding_provider,
        )
        payload = {
            "query": result.query,
            "top_k": result.top_k,
            "candidates": [
                {
                    "memory_id": item.memory_id,
                    "raw_distance": item.raw_distance,
                    "score": item.score,
                    "memory": item.memory,
                    "vector_metadata": item.vector_metadata.to_dict(),
                }
                for item in result.candidates
            ],
            "filtered_out": [
                {
                    "memory_id": item.memory_id,
                    "reason": item.reason,
                    "vector_metadata": item.vector_metadata.to_dict(),
                }
                for item in result.filtered_out
            ],
            "vector_index_status": result.vector_index_status,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
