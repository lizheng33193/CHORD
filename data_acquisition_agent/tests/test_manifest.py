"""test_manifest — Step 4 TDD."""

from pathlib import Path
import pytest
from data_acquisition_agent.manifest import load_manifest, CountryManifest, ManifestNotImplemented


@pytest.fixture(autouse=True)
def _default_to_production_manifest(monkeypatch):
    monkeypatch.delenv("DA_LOCAL_DEV", raising=False)


def test_mexico_manifest_loads():
    m = load_manifest("mexico")
    assert m.country == "mexico"
    assert m.sql_dialect == "starrocks"
    assert m.analyst_private_prefix == "dm_model.yyp_tmp_"
    for p in (m.business_logic_md, m.all_examples_md, m.schema_md, m.few_md, m.system_prompt_md):
        assert isinstance(p, Path) and p.exists(), p


def test_unknown_country_raises():
    with pytest.raises(FileNotFoundError):
        load_manifest("atlantis")


def test_placeholder_country_raises_manifest_not_implemented():
    # indonesia.yaml 当前为 placeholder（路径未填或为 <PLACEHOLDER_*>）
    with pytest.raises(ManifestNotImplemented):
        load_manifest("indonesia")
