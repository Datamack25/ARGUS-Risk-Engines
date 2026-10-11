"""Page Analyse : exécution du moteur, constats rédigés, tableau des transactions suspectes."""

import io
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from core import config as cfg
from core import enrichment, ui
from core.data import load_file, normalize
from core.engine import run_analysis
from core.narrative import build_findings
from core.report import build_docx, to_excel_bytes
from core.sample import demo_dataframe
from core.settings import load_settings

ui.banner("Alertes & résultats de l'analyse", cfg.APP_SUBTITLE, compact=True)

sources = st.session_state.get("sources")
if not sources:
    st.markdown('<div class="hero-desc">Aucun fichier à analyser. Retournez à l\'accueil pour en charger un.</div>',
                unsafe_allow_html=True)
    _, middle, _ = st.columns([1, 1, 1])
    with middle:
        ui.go_button("← Accueil", "views/home.py", "btn_home_empty")
    st.stop()


source_label = sources[0]["name"] if sources and len(sources) == 1 else \
    f"{len(sources or [])} fichiers consolidés" if sources else ""


def compute():
    settings = load_settings()
    frames, infos = [], []
    for src in sources:
        if src.get("demo"):
            raw = demo_dataframe()
        else:
            buffer = io.BytesIO(src["bytes"])
            buffer.name = src["name"]
            raw = load_file(buffer)
        frame, info = normalize(raw, settings.exclusions, src.get("mapping"), settings.fx_rates,
                                settings.header_synonyms)
        frame["FICHIER_SOURCE"] = src["name"]
        frames.append(frame)
        infos.append((src["name"], info))
    normalized = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    res = run_analysis(normalized, settings)
    context_notes = enrichment.apply_context(res, st.session_state.get("context"), settings)
    label = source_label
    findings = build_findings(res, label)
    notes = [f"{n} : {i['rows_file']} ligne(s) lue(s), {i['rows_analyzed']} analysée(s)." for n, i in infos]
    notes += [n for _, i in infos for n in i["notes"]] + context_notes
    docx_bytes = build_docx(res, label, notes)
    xlsx_bytes = to_excel_bytes({
        "Transactions suspectes": findings.table,
        "Operations": res.df, "Clients": res.clients, "Typologies": res.typology_status,
    })
    # Fichiers générés automatiquement : exports, journal des analyses, apprentissage (hors démonstration)
    demo_only = all(src.get("demo") for src in sources)
    generated = enrichment.save_exports(docx_bytes, xlsx_bytes)
    if enrichment.log_analysis(res, label, len(sources), settings):
        generated.append(enrichment.HISTORY_FILE)
    if not demo_only and enrichment.learn(res, label, settings):
        generated += [enrichment.PROFILES_FILE, enrichment.PATTERNS_FILE]
    return {
        "res": res, "infos": infos, "info": infos[0][1], "findings": findings, "when": datetime.now(),
        "context_notes": context_notes, "generated": generated, "demo_only": demo_only,
        "docx": docx_bytes, "xlsx": xlsx_bytes,
    }


if "result" not in st.session_state:
    try:
        with st.spinner("Analyse en cours…"):
            st.session_state["result"] = compute()
    except Exception as exc:
        st.error(f"Erreur d'analyse : {exc}")
        _, middle, _ = st.columns([1, 1, 1])
        with middle:
            ui.go_button("← Accueil", "views/home.py", "btn_home_error")
        st.stop()

stored = st.session_state["result"]
res, info, findings = stored["res"], stored["info"], stored["findings"]
df = res.df

# --------------------------------------------------------------- navigation
_, c_home, c_new, _ = st.columns([1, 1.4, 1.4, 1])
with c_home:
    ui.go_button("← Accueil", "views/home.py", "btn_home")
with c_new:
    if st.button("🔄 Nouvelle analyse", key="btn_new"):
        st.session_state.pop("result", None)
        st.session_state.pop("sources", None)
        st.switch_page("views/import_data.py")

st.caption(f"Source : {source_label} — analysé le {stored['when']:%d/%m/%Y à %H:%M} "
           f"— paramétrage v{res.settings.version}")

# --------------------------------------------------------------- verdict et indicateurs
n2 = int((df["NIVEAU"] == cfg.LEVEL_N2).sum())
n1 = int((df["NIVEAU"] == cfg.LEVEL_N1).sum())
ui.verdict("n2" if n2 else "n1" if len(findings.table) else "ok", findings.headline)
ui.kpis([
    ("Opérations analysées", len(df)),
    ("Volume analysé", ui.fmt_eur(df["MONTANT"].sum())),
    ("Opérations suspectes", len(findings.table)),
    ("Escalade N2", n2),
    ("Niveau N1", n1),
])

# --------------------------------------------------------------- fichiers générés
ui.section("Fichiers générés par l'analyse")
_, d1, d2, _ = st.columns([1, 2, 2, 1])
with d1:
    st.download_button("📝 Télécharger la note N2 (Word)", data=stored["docx"], key="dl_docx_top",
                       file_name=f"argus_note_N2_{stored['when']:%Y%m%d_%H%M}.docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
with d2:
    st.download_button("📊 Télécharger l'analyse (Excel)", data=stored["xlsx"], key="dl_xlsx_top",
                       file_name=f"argus_analyse_{stored['when']:%Y%m%d_%H%M}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
notes_gen = ("Fichiers enregistrés sur le serveur : " + ", ".join(stored["generated"]) + "."
             if stored["generated"] else "Aucun fichier enregistré sur le serveur : utilisez les boutons de téléchargement.")
if stored["demo_only"]:
    notes_gen += " (Les données de démonstration n'alimentent pas l'historique d'apprentissage.)"
st.caption(notes_gen + " Sur Streamlit Cloud, le disque est éphémère : téléchargez les fichiers à conserver.")

# --------------------------------------------------------------- constats rédigés
ui.section("Ce que le moteur a remarqué")
with st.container(key="card_findings"):
    st.write(findings.summary)
    if findings.details:
        st.markdown("**Détail par typologie déclenchée**")
        for paragraph in findings.details:
            st.markdown(f"- {paragraph}")
    st.write(findings.clients_paragraph)
    st.caption(findings.limits)

# --------------------------------------------------------------- tableau des transactions suspectes
ui.section("Transactions suspectes")
levels = st.multiselect("Niveaux affichés", cfg.LEVELS, default=cfg.LEVELS, key="levels_shown")
table = findings.table[findings.table["NIVEAU"].isin(levels)]
st.caption(f"{len(table)} transaction(s) — volume {ui.fmt_eur(table['MONTANT'].sum()) if len(table) else '0,00 €'}")
ui.show_table(table, empty="Aucune transaction suspecte pour ce filtre.")

# --------------------------------------------------------------- compléments
ui.section("Aller plus loin")
tab_synth, tab_ops, tab_export = st.tabs(["📊 Synthèse", "📋 Toutes les opérations", "📄 Exports"])

with tab_synth:
    left, right = st.columns(2)
    with left:
        st.markdown("**Répartition par niveau de risque**")
        counts = df["NIVEAU"].value_counts()
        ui.bars([(level, int(counts.get(level, 0))) for level in cfg.LEVELS])
    with right:
        st.markdown("**Alertes par famille de risque**")
        by_family = (res.typology_status.groupby("Famille")["Alertes"].sum()
                     .sort_values(ascending=False))
        ui.bars([(family, int(n)) for family, n in by_family.items()])
    st.markdown("**Profils clients à surveiller**")
    watch = res.clients[res.clients["Niveau"] != cfg.LEVEL_LOW].head(15)
    ui.show_table(watch, empty="Aucun client au-dessus du seuil modéré.")
    st.markdown("**Couverture et résultats par typologie**")
    ui.show_table(res.typology_status, max_rows=100)
    st.markdown("**Qualité des données et décompte des lignes**")
    for name, inf in stored["infos"]:
        st.write(f"• {name} : {inf['rows_file']} lue(s) · {inf['rows_empty']} vide(s) · {inf['rows_invalid']} illisible(s) · "
                 f"{inf['rows_excluded']} exclue(s) · **{inf['rows_analyzed']} analysée(s)**")
        for note in inf["notes"]:
            st.write(f"   – {note}")
        if inf["unrecognized"]:
            st.write("   – Colonnes non utilisées : " + ", ".join(inf["unrecognized"]))
    for note in stored["context_notes"]:
        st.write(f"• Contexte : {note}")

with tab_ops:
    f1, f2 = st.columns(2)
    with f1:
        direction = "Tous"
        if "SENS" in df.columns:
            direction = st.radio("Sens", ["Tous", "Entrants", "Sortants"], horizontal=True)
        min_score = st.slider("Score minimal", 0, res.settings.cap, 0)
    with f2:
        triggered = [c for c, f in res.flags.items() if f.any()]
        picked = st.multiselect("Typologie déclenchée", triggered,
                                format_func=lambda c: f"{c} — {res.codes_to_names[c]}")
        query = st.text_input("Recherche (client, libellé, contrepartie…)")
    mask = df["RISK_SCORE"] >= min_score
    if direction == "Entrants":
        mask &= df["SENS"] == "ENTRANT"
    elif direction == "Sortants":
        mask &= df["SENS"] == "SORTANT"
    if picked:
        mask &= np.any([res.flags[c] for c in picked], axis=0)
    if query.strip():
        cols = [c for c in ("ID_CLIENT", "NOM_CLIENT", "LIBELLE", "CONTREPARTIE", "ID_TRANSACTION")
                if c in df.columns]
        mask &= df[cols].astype(str).agg(" ".join, axis=1).str.contains(query.strip(), case=False, regex=False)
    view = df[mask].sort_values("RISK_SCORE", ascending=False)
    shown_cols = [c for c in ["ID_TRANSACTION", "DATE", "ID_CLIENT", "NOM_CLIENT", "LIBELLE", "CONTREPARTIE",
                              "IBAN_CONTREPARTIE", "MONTANT", "SENS", "PAYS", "RISK_SCORE", "NIVEAU", "ALERTES", "QUALIFICATION", "FICHIER_SOURCE"] if c in view.columns]
    st.caption(f"{len(view)} opération(s) — volume {ui.fmt_eur(view['MONTANT'].sum()) if len(view) else '0,00 €'}")
    ui.show_table(view[shown_cols].rename(columns={"ALERTES": "POURQUOI (typologies détectées)"}))

with tab_export:
    st.write(findings.summary)
    st.write(findings.clients_paragraph)
    _, d1, d2, _ = st.columns([1, 2, 2, 1])
    with d1:
        st.download_button("📝 Exporter la note (Word)", data=stored["docx"], key="dl_docx",
                           file_name="argus_risk_note_N2.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with d2:
        st.download_button("📊 Exporter les données (Excel)", data=stored["xlsx"], key="dl_xlsx",
                           file_name="argus_risk_analyse.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
