"""Tests de non-régression du moteur unifié (46 typologies)."""

import pandas as pd
import pytest

from core.data import normalize
from core.engine import run_analysis
from core.narrative import build_findings
from core.report import build_docx
from core.sample import demo_dataframe
from core.typologies import DETECTOR_REQUIRES, TYPOLOGIES
from core.engine import DETECTORS


def test_catalogue_size_and_detectors():
    assert len(TYPOLOGIES) >= 30
    assert len({t.code for t in TYPOLOGIES}) == len(TYPOLOGIES)
    for t in TYPOLOGIES:
        assert t.detector in DETECTORS and t.detector in DETECTOR_REQUIRES


def test_demo_triggers_every_typology():
    df, info = normalize(demo_dataframe())
    res = run_analysis(df)
    status = res.typology_status
    assert (status["Statut"] == "Erreur").sum() == 0
    assert (status["Statut"] == "Non évaluable").sum() == 0
    assert (status["Alertes"] == 0).sum() == 0
    assert res.df["RISK_SCORE"].between(0, 100).all()
    assert info["rows_excluded"] >= 2


def test_findings_paragraph_and_table():
    df, _ = normalize(demo_dataframe())
    res = run_analysis(df)
    f = build_findings(res, "demo")
    assert "suspecte" in f.headline and len(f.summary) > 100
    assert len(f.details) == len(TYPOLOGIES)
    assert len(f.table) == int((res.df["NB_TYPOLOGIES"] > 0).sum())
    assert "ID_TRANSACTION" in f.table.columns
    assert len(build_docx(res, "demo")) > 5000


def test_missing_columns_are_reported_not_ignored():
    df, _ = normalize(demo_dataframe()[["DATE", "ID_CLIENT", "NOM_CLIENT", "LIBELLE", "MONTANT", "SENS"]])
    res = run_analysis(df)
    assert (res.typology_status["Statut"] == "Non évaluable").any()


def test_clean_file_has_no_findings():
    df, _ = normalize(pd.DataFrame({"MONTANT": [10, 20, 30], "SENS": ["CREDIT", "DEBIT", "CREDIT"]}))
    f = build_findings(run_analysis(df), "propre")
    assert len(f.table) == 0 and "Aucune" in f.headline


def test_missing_amount_column_raises():
    with pytest.raises(ValueError):
        normalize(pd.DataFrame({"A": [1, 2]}))
