"""Tests de l'administration : validation, publication versionnée, audit, effet sur le moteur."""

import copy

import pytest

from core import settings as cs
from core.data import normalize
from core.engine import run_analysis
from core.sample import demo_dataframe


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(tmp_path))


def test_default_config_is_valid():
    assert cs.validate_config(cs.default_config()) == []
    assert cs.dry_run(cs.default_config()) == []


def test_publish_versions_and_audits():
    draft = cs.load_config()
    draft["thresholds"]["n1"] = 35
    draft["typologies"]["FRA-05"]["params"]["threshold"] = 5000
    new = cs.publish(draft, "Head of Compliance", "Calibrage")
    assert new["version"] == 1
    assert cs.load_settings().n1 == 35
    audit = cs.read_audit()
    assert len(audit) == 1 and len(audit[0]["changes"]) == 2
    assert cs.read_history()[0]["config"]["version"] == 1


def test_publish_requires_author_and_reason():
    with pytest.raises(ValueError):
        cs.publish(cs.load_config(), "", "motif")
    with pytest.raises(ValueError):
        cs.publish(cs.load_config(), "auteur", " ")


def test_invalid_configs_are_refused():
    bad = copy.deepcopy(cs.load_config())
    bad["thresholds"]["n1"] = 90
    with pytest.raises(ValueError):
        cs.publish(bad, "a", "b")
    bad = cs.load_config()
    bad["custom_typologies"].append({"code": "CUS-01", "name": "x", "weight": 10, "detector": "nope", "params": {}})
    with pytest.raises(ValueError):
        cs.publish(bad, "a", "b")


def test_settings_change_engine_behaviour():
    frame, _ = normalize(demo_dataframe())
    base = run_analysis(frame, cs.load_settings())
    draft = cs.load_config()
    draft["typologies"]["SAN-01"]["enabled"] = False
    draft["custom_typologies"].append({"code": "CUS-01", "name": "Gros virement", "weight": 40,
                                       "detector": "large_single", "params": {"threshold": 9999}, "enabled": True})
    draft["whitelist"].append({"id": "S07", "reason": "test", "added_at": "x"})
    cs.publish(draft, "a", "b")
    changed = run_analysis(frame, cs.load_settings())
    status = changed.typology_status.set_index("Code")["Alertes"]
    assert "SAN-01" not in status.index and status["CUS-01"] > 0
    assert changed.df[changed.df.ID_CLIENT == "S07"]["NB_TYPOLOGIES"].sum() == 0
    assert changed.settings.version == 1 and base.settings.version == 0


def test_admin_password_gate(monkeypatch):
    monkeypatch.delenv("ARGUS_ADMIN_PASSWORD", raising=False)
    assert not cs.check_admin_password("anything") or cs.admin_password() != ""
    monkeypatch.setenv("ARGUS_ADMIN_PASSWORD", "s3cret")
    assert cs.check_admin_password("s3cret") and not cs.check_admin_password("wrong")
