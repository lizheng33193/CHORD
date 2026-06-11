"""Interactive LLM smoke test for this repo.

Usage:
  python test.py

This script loads `.env` via app.core.config, then sends your prompt to the
configured provider (Vertex AI or Gemini API key) and prints the model output.
"""

from __future__ import annotations

import os
import sys


def _build_client():
    from app.core.config import settings

    try:
        from google import genai
    except Exception as exc:  # pylint: disable=broad-except
        try:
            import google_genai as genai  # type: ignore
        except Exception:  # pylint: disable=broad-except
            raise RuntimeError(
                "google-genai is not installed in the current environment. "
                "Install requirements.txt into your active venv/conda env."
            ) from exc

    mode = settings.model_mode
    model_name = settings.resolved_model_name

    if mode in {"vertex", "vertexai", "gemini-vertex"}:
        creds = settings.resolved_google_application_credentials
        if creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
        if not settings.vertex_project_id:
            raise RuntimeError("VERTEX_PROJECT_ID is missing in .env for MODEL_MODE=vertex")
        client = genai.Client(
            vertexai=True,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
        )
        return client, model_name, f"vertex project={settings.vertex_project_id} location={settings.vertex_location}"

    if mode == "gemini":
        api_key = settings.resolved_gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing in .env for MODEL_MODE=gemini")
        client = genai.Client(api_key=api_key)
        return client, model_name, "gemini api-key"

    raise RuntimeError(f"Unsupported MODEL_MODE={mode}. Use vertex/gemini/mock.")


def main() -> int:
    print("LLM smoke test (type 'exit' to quit)\n")
    client, model, provider = _build_client()
    print(f"Provider: {provider}")
    print(f"Model:    {model}\n")

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            return 0

        try:
            response = client.models.generate_content(model=model, contents=user_input)
            text = getattr(response, "text", None) or ""
            if not text:
                candidates = getattr(response, "candidates", None)
                text = str(candidates) if candidates is not None else ""
            print(f"\nModel> {text}\n")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"\n[ERROR] {exc}\n", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
