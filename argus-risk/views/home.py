"""Accueil : onboarding au premier lancement, sinon tableau de bord exécutif."""

import pandas as pd
import streamlit as st

from core import config as cfg
from core import enrichment, ui
from core.engine import QUAL_CLIENT, QUAL_PUBLIC, QUAL_WHITELIST
from core.settings import load_settings

PLATFORM = "Compliance & Fraud Intelligence Platform"
settings = load_settings()
history = enrichment.load_history()
stored = st.session_state.get("result")
first_launch = history.empty and not stored

ui.banner("🛡️ Argus RISK", PLATFORM, compact=True)


def start_demo():
    st.session_state["sources"] = [{"name": "Données de démonstration", "bytes": None, "demo": True, "mapping": None}]
    st.session_state.pop("result", None)
    st.switch_page("views/analysis.py")


# ======================================================================== 1) premier lancement
if first_launch:
    sectors = enrichment.load_sectors()
    n_labels = len(settings.whitelist_rules.get("labels", []))
    badges = [
        ("ok", f"Moteur de règles opérationnel — {len(settings.typologies)} typologies actives"),
        ("ok" if n_labels or settings.public_entities else "warn",
         f"Whitelist active — {n_labels} libellé(s), {len(settings.public_entities)} entité(s) publique(s)"),
        ("ok" if len(sectors) else "warn", f"Référentiels secteurs chargés — {len(sectors)} secteur(s)"),
    ]
    chips = "".join(f'<span class="{"wl-badge" if k == "ok" else "mod-badge"}">{"✔" if k == "ok" else "⚠"} {t}</span>'
                    for k, t in badges)
    ui.card("👋 Bienvenue sur Argus RISK",
            '<div class="dcard-muted" style="font-size:1rem;margin-bottom:.8rem">Votre moteur d\'analyse transactionnelle '
            'LCB-FT &amp; Anti-Fraude : importez vos transactions, le moteur relève les opérations suspectes, '
            'rédige les constats et génère les livrables.</div>'
            f'<div style="margin-bottom:.4rem">{chips}</div>')
    ui.card("🚀 Démarrer une première analyse",
            '<div class="dcard-muted">Importez un ou plusieurs fichiers de transactions (Excel / CSV), '
            'ou testez l\'outil avec des données de démonstration.</div>')
    c1, c2, c3 = st.columns(3)
    with c1:
        ui.go_button("🚀 Lancer votre première analyse", "views/import_data.py", "btn_first")
    with c2:
        if st.button("🧪 Charger des données de démonstration", key="btn_first_demo"):
            start_demo()
    with c3:
        ui.go_button("📋 Remplir le KYC", "views/kyc_input.py", "btn_first_kyc")
    st.stop()

# ======================================================================== 2) tableau de bord exécutif
h = history.copy()
for col in ("rows", "volume", "suspects", "n1", "n2", "exempt", "clients_flagged", "files"):
    h[col] = pd.to_numeric(h[col], errors="coerce").fillna(0)
rows_total = int(h["rows"].sum()) if len(h) else 0
exempt_rate = (h["exempt"].sum() / rows_total * 100) if rows_total else 0.0

ui.section("Tableau de bord exécutif")
ui.kpis([
    ("Analyses effectuées", len(h)),
    ("Opérations traitées", f"{rows_total:,}".replace(",", " ")),
    ("Volume traité", ui.fmt_eur(float(h["volume"].sum()))),
    ("Opérations suspectes", int(h["suspects"].sum())),
    ("Escalades N2", int(h["n2"].sum())),
    ("Taux d'exemption whitelist", f"{exempt_rate:.1f} %".replace(".", ",")),
])

ui.section("Dernières analyses")
last = h.sort_values("analysis_date", ascending=False).head(10).copy()
last["Date"] = pd.to_datetime(last["analysis_date"], errors="coerce")
table = pd.DataFrame({
    "Date": last["Date"], "Source": last["source"], "Fichiers": last["files"].astype(int),
    "Opérations": last["rows"].astype(int), "Volume": last["volume"],
    "Suspectes": last["suspects"].astype(int), "Niveau N2": last["n2"].astype(int),
    "Exemptions": last["exempt"].astype(int),
})
ui.show_table(table, empty="Aucune analyse enregistrée.")

if stored:
    res, df = stored["res"], stored["res"].df
    left, right = st.columns(2, gap="large")
    with left:
        ui.card("Réduction des faux positifs (dernière analyse)", "")
        ui.bars([(QUAL_WHITELIST, int((df["QUALIFICATION"] == QUAL_WHITELIST).sum())),
                 (QUAL_PUBLIC, int((df["QUALIFICATION"] == QUAL_PUBLIC).sum())),
                 (QUAL_CLIENT, int((df["QUALIFICATION"] == QUAL_CLIENT).sum())),
                 ("Alertes conservées", int((df["NB_TYPOLOGIES"] > 0).sum()))])
    with right:
        ui.card("Alertes par famille de risque (dernière analyse)", "")
        by_family = res.typology_status.groupby("Famille")["Alertes"].sum().sort_values(ascending=False)
        ui.bars([(f, int(n)) for f, n in by_family.head(6).items()])
    ui.section("Dernières alertes LCB-FT")
    latest = stored["findings"].table.copy()
    if "DATE" in latest.columns:
        latest = latest.sort_values("DATE", ascending=False)
    cols = [c for c in ["DATE", "ID_CLIENT", "NOM_CLIENT", "CONTREPARTIE", "IBAN_CONTREPARTIE", "MONTANT",
                        "POURQUOI (typologies détectées)", "RISK_SCORE"] if c in latest.columns]
    ui.show_table(latest[cols].rename(columns={"POURQUOI (typologies détectées)": "Type de risque"}).head(10),
                  empty="Aucune alerte.")

c1, c2, c3 = st.columns(3)
with c1:
    ui.go_button("📥 Nouvelle analyse", "views/import_data.py", "btn_home_new")
with c2:
    ui.go_button("🚨 Alertes & analyse", "views/analysis.py", "btn_home_alerts")
with c3:
    if st.button("🧪 Données de démonstration", key="btn_home_demo"):
        start_demo()
