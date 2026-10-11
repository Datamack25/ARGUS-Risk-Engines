"""Page Import de données : un ou plusieurs fichiers, mapping dynamique des en-têtes, lancement de l'analyse."""

import html
import io

import streamlit as st

from core import config as cfg
from core import profiles, ui
from core.data import CANONICAL, FIELD_LABELS, detect_mapping, load_file, normalize
from core.sample import template_dataframe
from core.settings import load_settings

NONE = "— non mappé —"
FIELDS = list(CANONICAL)
settings = load_settings()

ui.banner("🛡️ Argus RISK", "Compliance & Fraud Intelligence Platform", compact=True)
st.markdown('<div class="hero-desc">Import de données — chargez un ou plusieurs fichiers (CSV ou Excel) puis lancez l\'analyse.</div>',
            unsafe_allow_html=True)

# ------------------------------------------------------------------ téléversement + bouton Analyser (même ligne)
with st.container(key="upload_card"):
    up_col, go_col = st.columns([4, 1], vertical_alignment="center", gap="medium")
    with up_col:
        uploads = st.file_uploader("Choisir un ou plusieurs fichiers", type=["csv", "xlsx", "xls"],
                                   accept_multiple_files=True, label_visibility="collapsed", key="uploader")
    with go_col:
        go_slot = st.empty()
    count = len(uploads or [])
    st.markdown(f'<div class="status-line">{count} fichier(s) prêt(s)</div>' if count else
                '<div class="status-line">Aucun fichier choisi — glissez-déposez un ou plusieurs fichiers</div>',
                unsafe_allow_html=True)

# ------------------------------------------------------------------ 4 boutons alignés
b1, b2, b3, b4 = st.columns(4)
with b1:
    st.download_button("📄 Modèle de fichier",
                       data=template_dataframe().to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name="argus_modele_fichier.csv", mime="text/csv", key="dl_template")
with b2:
    ui.go_button("📘 Guide d'utilisation", "views/guide.py", "btn_guide")
with b3:
    demo = st.button("🧪 Démonstration", key="btn_demo")
with b4:
    ui.go_button("📋 Remplir le KYC", "views/kyc_input.py", "btn_kyc")
st.write("")

left, right = st.columns([3, 2], gap="large")

# ------------------------------------------------------------------ colonne droite : entités légitimes
with right:
    labels = settings.whitelist_rules.get("labels", [])
    entities = [e["name"] for e in settings.public_entities]
    ui.card("Entités légitimes & liste blanche",
            '<div class="dcard-muted">Opérations récurrentes validées (aucune alerte, score 0) :</div>'
            + ui.wl_badges(labels[:12]) +
            '<div class="dcard-muted" style="margin-top:.6rem">Entités publiques (IBAN du pays cohérent exigé) :</div>'
            + ui.wl_badges(entities[:8]) +
            f'<div class="dcard-muted" style="margin-top:.6rem">Fenêtre comportementale : {settings.window_n} dernières '
            f'transactions par client. Réglages : Paramètres (Admin).</div>')
    ui.card("Comment ça marche",
            '<div class="dcard-muted">1. Chargez vos fichiers — plusieurs fichiers sont analysés ensemble.<br>'
            '2. Vérifiez le mapping des en-têtes (reconnaissance automatique, ajustable).<br>'
            '3. Cliquez sur <b>Analyser</b> : constats, tableau des transactions, exports.</div>')

# ------------------------------------------------------------------ colonne gauche : import
with left:
    cache = st.session_state.setdefault("raw_cache", {})
    sources, blocked = [], False
    report_rows = []

    for up in uploads or []:
        fkey = f"{up.name}:{up.size}"
        if fkey not in cache:
            try:
                buf = io.BytesIO(up.getvalue())
                buf.name = up.name
                cache[fkey] = {"raw": load_file(buf), "bytes": up.getvalue(), "error": None}
            except Exception as exc:
                cache[fkey] = {"raw": None, "bytes": None, "error": str(exc)}
        item = cache[fkey]
        with st.expander(f"📄 {up.name}", expanded=True):
            if item["error"]:
                st.error(f"Fichier illisible : {item['error']}")
                blocked = True
                continue
            raw = item["raw"]
            cols = list(raw.columns)
            keyf = lambda f: f"map|{fkey}|{f}"

            def set_mapping(mapping):
                for f in FIELDS:
                    st.session_state[keyf(f)] = mapping.get(f, NONE)

            def auto(saved=None):
                det = detect_mapping(cols, saved=saved, synonyms=settings.header_synonyms)
                set_mapping(det["mapping"])

            def on_profile():
                name = st.session_state.get(f"prof|{fkey}")
                if name and name != NONE:
                    auto(saved=profiles.load().get(name, {}).get("mapping", {}))

            if f"init|{fkey}" not in st.session_state:
                auto()
                st.session_state[f"init|{fkey}"] = True
            detection = detect_mapping(cols, synonyms=settings.header_synonyms)
            methods = {d["field"]: d for d in detection["details"]}

            mapping = {f: st.session_state[keyf(f)] for f in FIELDS
                       if st.session_state.get(keyf(f), NONE) in cols}
            used = list(mapping.values())
            duplicated = sorted({c for c in used if used.count(c) > 1})

            # --- carte « Mapping dynamique des en-têtes »
            rows = []
            for f in FIELDS:
                if f in mapping:
                    d = methods.get(f)
                    if d and d["header"] == mapping[f]:
                        tag = ('<span class="m-ok">✔ Match automatique</span>' if d["method"] in ("exacte", "alias")
                               else f'<span class="m-fz">≈ Approximatif ({int(d["score"] * 100)} %)</span>')
                    else:
                        tag = '<span class="m-ok">✔ Choix manuel / profil</span>'
                    rows.append(f"<tr><td>{html.escape(FIELD_LABELS.get(f, f))}</td>"
                                f"<td>{html.escape(mapping[f])}</td><td>{tag}</td></tr>")
                elif f == "MONTANT":
                    rows.append(f"<tr><td>{html.escape(FIELD_LABELS['MONTANT'])}</td><td>—</td>"
                                '<td><span class="m-no">✖ À choisir ci-dessous</span></td></tr>')
            auto_n = sum(1 for f, d in methods.items() if mapping.get(f) == d["header"])
            ui.card("Mapping dynamique des en-têtes",
                    f'<div class="dcard-muted">{len(cols)} colonne(s) dans le fichier · {len(mapping)} reconnue(s) · '
                    f'{auto_n} par correspondance automatique</div>'
                    '<table class="map"><thead><tr><th>Champ standard</th><th>Colonne du fichier</th><th>Statut</th></tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody></table>')
            if duplicated:
                st.warning("Une même colonne est affectée à plusieurs champs : " + ", ".join(duplicated))

            with st.expander("Ajuster le mapping (listes déroulantes)", expanded="MONTANT" not in mapping):
                grid = st.columns(3)
                for i, f in enumerate(FIELDS):
                    with grid[i % 3]:
                        st.selectbox(FIELD_LABELS.get(f, f), [NONE] + cols, key=keyf(f))
                b1, b2, b3 = st.columns(3)
                with b1:
                    st.button("✨ Match automatique", key=f"auto|{fkey}", on_click=auto)
                saved = profiles.load()
                with b2:
                    st.selectbox("Profil client enregistré", [NONE] + sorted(saved), key=f"prof|{fkey}",
                                 on_change=on_profile)
                with b3:
                    pname = st.text_input("Enregistrer sous (nom du client / format)", key=f"pname|{fkey}")
                    if st.button("💾 Enregistrer le profil", key=f"psave|{fkey}"):
                        if pname.strip():
                            profiles.save_profile(pname.strip(), mapping)
                            st.success(f"Profil « {pname.strip()} » enregistré.")
                        else:
                            st.warning("Donnez un nom au profil.")

            # --- comptage exact des lignes
            try:
                _, info = normalize(raw, settings.exclusions, mapping, settings.fx_rates, settings.header_synonyms)
                report_rows.append((up.name, info))
                sources.append({"name": up.name, "bytes": item["bytes"], "demo": False, "mapping": mapping})
            except ValueError as exc:
                st.error(str(exc))
                blocked = True

    if report_rows:
        body = "".join(
            f"<tr><td>{html.escape(n)}</td><td>{i['rows_file']}</td><td>{i['rows_empty']}</td>"
            f"<td>{i['rows_invalid']}</td><td>{i['rows_excluded']}</td><td><b>{i['rows_analyzed']}</b></td>"
            f"<td>{'✔' if i['rows_file'] == i['rows_empty'] + i['rows_invalid'] + i['rows_excluded'] + i['rows_analyzed'] else '✖'}</td></tr>"
            for n, i in report_rows)
        total = sum(i["rows_analyzed"] for _, i in report_rows)
        ui.card("Rapport d'import — décompte des lignes",
                '<table class="map"><thead><tr><th>Fichier</th><th>Lignes lues</th><th>Vides / parasites</th>'
                '<th>Montant illisible</th><th>Exclues (frais, rejets…)</th><th>Analysées</th><th>Contrôle</th></tr></thead>'
                f'<tbody>{body}</tbody></table>'
                f'<div class="dcard-muted" style="margin-top:.5rem">Total à analyser : <b>{total}</b> opération(s) '
                f'sur {len(report_rows)} fichier(s).</div>')

go = go_slot.button("📊 Analyser", key="btn_analyze", disabled=not sources or blocked)

if go and sources:
    st.session_state["sources"] = sources
    st.session_state.pop("result", None)
    st.switch_page("views/analysis.py")
if demo:
    st.session_state["sources"] = [{"name": "Données de démonstration", "bytes": None, "demo": True, "mapping": None}]
    st.session_state.pop("result", None)
    st.switch_page("views/analysis.py")
