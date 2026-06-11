"""Country manifest loader. See Design Doc §6.1."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


CONFIG_DIR = Path(__file__).resolve().parent / "configs"
REQUIRED_MD = ("business_logic_md", "all_examples_md", "schema_md", "few_md", "system_prompt_md")
REQUIRED_FIELDS = REQUIRED_MD + ("country", "display_name", "sql_dialect", "analyst_private_prefix")
REPO_ROOT = Path(__file__).resolve().parent.parent


class ManifestNotImplemented(Exception):
    """Raised when a country YAML is a placeholder/empty/missing required fields.
    Caller maps to ErrorType.BAD_REQUEST."""


@dataclass
class CountryManifest:
    country: str
    display_name: str
    business_logic_md: Path
    all_examples_md: Path
    schema_md: Path
    few_md: Path
    system_prompt_md: Path
    sql_dialect: str
    analyst_private_prefix: str

    @classmethod
    def from_yaml(cls, path: Path) -> "CountryManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ManifestNotImplemented(f"{path.name}: empty or non-dict yaml")
        for k in REQUIRED_FIELDS:
            if k not in data or data[k] is None:
                raise ManifestNotImplemented(f"{path.name}: missing field {k}")
            if isinstance(data[k], str) and data[k].startswith("<PLACEHOLDER"):
                raise ManifestNotImplemented(f"{path.name}: placeholder field {k}")
        kwargs = {k: REPO_ROOT / data[k] for k in REQUIRED_MD}
        for k, p in kwargs.items():
            if not p.exists():
                raise ManifestNotImplemented(f"{path.name}: {k} path does not exist {p}")
        return cls(
            country=data["country"],
            display_name=data["display_name"],
            sql_dialect=data["sql_dialect"],
            analyst_private_prefix=data["analyst_private_prefix"],
            **kwargs,
        )


def resolve_knowledge_namespace(country: str) -> str:
    """Return the knowledge-base namespace for routing/indexing.

    When DA_LOCAL_DEV=1 and a country-specific local manifest exists,
    knowledge routing should use the shared local_dev INDEX/md set instead of
    the production country directory. Manifest loading still happens via the
    original business country (`mexico` -> `mexico.local.yaml`).
    """
    if os.environ.get("DA_LOCAL_DEV") == "1":
        local_p = CONFIG_DIR / f"{country}.local.yaml"
        if local_p.exists():
            return "local_dev"
    return country


def load_manifest(country: str) -> CountryManifest:
    # 2026-05-04: opt-in local-dev override. When DA_LOCAL_DEV=1 is set,
    # prefer `{country}.local.yaml` (points to a 3-table local MySQL schema)
    # over the production `{country}.yaml`. Production tests / CI still
    # default-load the production manifest because the env var is absent.
    if os.environ.get("DA_LOCAL_DEV") == "1":
        local_p = CONFIG_DIR / f"{country}.local.yaml"
        if local_p.exists():
            return CountryManifest.from_yaml(local_p)
    p = CONFIG_DIR / f"{country}.yaml"
    if not p.exists():
        raise FileNotFoundError(p)
    return CountryManifest.from_yaml(p)


def list_registered_countries() -> list[str]:
    return sorted(
        p.stem for p in CONFIG_DIR.glob("*.yaml")
        if not p.name.endswith(".local.yaml")
    )
