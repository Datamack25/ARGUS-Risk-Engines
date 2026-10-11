import pandas as pd

from core import enrichment
from core.data import detect_mapping, normalize
from core.engine import QUAL_PUBLIC, QUAL_WHITELIST, run_analysis
from core.sample import demo_dataframe
from core.settings import load_settings


def test_fuzzy_and_synonyms():
    det = detect_mapping(["Montnt_TTC", "Beneficiare", "Total facture"], synonyms={"MONTANT": ["Total facture"]})
    assert det["mapping"]["CONTREPARTIE"] == "Beneficiare"
    assert "MONTANT" in det["mapping"]


def test_row_accounting_with_blank_rows():
    raw = pd.DataFrame({"Montant": [10, 20, None, "abc", 30], "Libellé": ["A", "B", "", "C", "FRAIS BANCAIRES"]})
    raw.loc[len(raw)] = [None, None]
    _, info = normalize(raw, ["FRAIS"])
    assert info["rows_file"] == info["rows_empty"] + info["rows_invalid"] + info["rows_excluded"] + info["rows_analyzed"]
    assert info["rows_empty"] == 2 and info["rows_analyzed"] == 2


def test_public_entity_whitelist_and_fake_rib():
    settings = load_settings()
    df, _ = normalize(demo_dataframe(), settings.exclusions)
    res = run_analysis(df, settings)
    s22 = res.df[res.df.ID_CLIENT == "S22"].iloc[0]
    assert s22["RISK_SCORE"] >= 95 and "FRD-10" in s22["ALERTES"]
    s23 = res.df[res.df.ID_CLIENT == "S23"]
    assert (s23["RISK_SCORE"] == 0).all()
    assert set(s23["QUALIFICATION"]) == {QUAL_PUBLIC, QUAL_WHITELIST}


def test_multi_file_consolidation_and_context(tmp_path, monkeypatch):
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(tmp_path))
    settings = load_settings()
    a, _ = normalize(demo_dataframe().iloc[:150], settings.exclusions)
    b, _ = normalize(demo_dataframe().iloc[150:], settings.exclusions)
    both = pd.concat([a.assign(FICHIER_SOURCE="a"), b.assign(FICHIER_SOURCE="b")], ignore_index=True)
    res = run_analysis(both, settings)
    before = int(res.df["RISK_SCORE"].sum())
    notes = enrichment.apply_context(res, {"kyc": {"ppe": True}, "transaction": {"secteur_contrepartie": "Crypto-actifs / PSAN"}}, settings)
    assert notes and int(res.df["RISK_SCORE"].sum()) > before
    assert enrichment.learn(res, "test", settings) > 0
    assert len(enrichment.load_csv(enrichment.PATTERNS_FILE, enrichment.PATTERN_COLS)) > 0


def test_iban_in_findings_and_history(tmp_path, monkeypatch):
    from core.narrative import build_findings
    monkeypatch.setenv("ARGUS_CONFIG_DIR", str(tmp_path))
    settings = load_settings()
    df, _ = normalize(demo_dataframe(), settings.exclusions)
    res = run_analysis(df, settings)
    f = build_findings(res, "demo")
    assert "IBAN_CONTREPARTIE" in f.table.columns and "CONTREPARTIE" in f.table.columns
    assert any("IBAN" in d for d in f.details)
    assert enrichment.log_analysis(res, "demo", 1, settings)
    hist = enrichment.load_history()
    assert len(hist) == 1 and int(hist.iloc[0]["rows"]) == len(res.df)
    assert enrichment.save_exports(b"x", b"y") and (tmp_path / "exports").exists()
