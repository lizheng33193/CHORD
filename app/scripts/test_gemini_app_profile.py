"""Smoke-test script for the App profile Gemini prompt flow."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.model_client import ModelClient
from app.repositories.local_repository import LocalUserRepository
from app.runtime_skills.app_profile_agent import AppProfileSkill


def main() -> None:
    uid = sys.argv[1] if len(sys.argv) > 1 else "824812551379353600"
    application_time = sys.argv[2] if len(sys.argv) > 2 else "2026-04-15T12:00:00Z"

    repository = LocalUserRepository()
    model_client = ModelClient()
    skill = AppProfileSkill(model_client)

    result = skill.analyze(uid=uid, repository=repository, application_time=application_time)
    print("=== summary ===")
    print(result["summary"])
    print("\n=== charts ===")
    print(json.dumps(result["charts"], ensure_ascii=False, indent=2))
    print("\n=== report_markdown ===")
    print(result["report_markdown"])


if __name__ == "__main__":
    main()
