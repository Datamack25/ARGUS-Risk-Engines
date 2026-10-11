"""Page Administration (Head of Compliance) : scores, typologies, listes, liste blanche, simulation, publication."""

import copy
import json
import re

import pandas as pd
import streamlit as st

from core import config as cfg
from core import settings as cs
from core import enrichment, ui
from core.data import load_file, normalize
from core.engine import run_analysis
from core.report import to_excel_bytes
from core.sample import demo_dataframe
from core.typologies import DETECTOR_REQUIRES, FAMILIES, TYPOLOGIES, COLUMN_LABELS

ui.banner("Administration", "Paramétrage réservé au Head of Compliance", compact=True)
_, left, _ = st.columns([1, 1, 1])
with left:
    ui.go_button("← Accueil", "views/home.py", "btn_back_admin")

# ======================================================================== accès
if not st.session_state.get("admin_ok"):
    with st.container(key="card_guide"):
        if not cs.admin_password():
            st.markdown("### 🔒 Accès non configuré")
            st.markdown(
                "Aucun mot de passe administrateur n'est défini. Dans **Streamlit Cloud** : *Manage app → Settings → "
                "Secrets*, puis ajoutez :")
            st.code('ADMIN_PASSWORD = "choisissez-un-mot-de-passe-long"', language="toml")
            st.markdown("En local, vous pouvez aussi définir la variable d'environnement `ARGUS_ADMIN_PASSWORD`. "
                        "Redémarrez ensuite l'application.")
        else:
            st.markdown("### 🔐 Connexion administrateur")
            attempts = st.session_state.get("admin_attempts", 0)
            if attempts >= 5:
                st.error("Trop de tentatives. Rechargez la page pour réessayer.")
            else:
                with st.form("admin_login"):
                    password = st.text_input("Mot de passe", type="password")
                    ok = st.form_submit_button("Se connecter")
                if ok:
                    if cs.check_admin_password(password):
                        st.session_state["admin_ok"] = True
                        st.session_state["admin_attempts"] = 0
                        st.rerun()
                    st.session_state["admin_attempts"] = attempts + 1
                    st.error("Mot de passe incorrect.")
    st.stop()

# ======================================================================== état
published = cs.load_config()
if "draft" not in st.session_state:
    st.session_state["draft"] = copy.deepcopy(published)
draft = st.session_state["draft"]
changes = cs.diff_configs(published, draft)

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))


def saved(message: str):
    st.session_state["flash"] = message + " (brouillon — à publier dans l'onglet « Publication »)"
    st.rerun()


c1, c2 = st.columns([3, 1])
with c1:
    last = published.get("updated_at") or "jamais"
    st.caption(f"Version publiée : v{published['version']} — dernière modification : {last} "
               f"par {published.get('updated_by') or '—'}")
    if changes:
        st.warning(f"Brouillon : {len(changes)} modification(s) non publiée(s).")
    else:
        st.info("Brouillon identique à la version publiée.")
with c2:
    if st.button("Se déconnecter", key="btn_logout"):
        for key in ("admin_ok", "draft"):
            st.session_state.pop(key, None)
        st.rerun()

tabs = st.tabs(["📊 Vue d'ensemble", "🎚️ Scores & seuils", "🧬 Typologies", "🌍 Listes de référence",
                "🛡️ Liste blanche", "⚙️ Import & contexte", "🧪 Simulation", "🚀 Publication & historique"])
t_over, t_score, t_typo, t_lists, t_white, t_adv, t_sim, t_pub = tabs

# ======================================================================== utilitaires
PARAM_LABELS = {
    "threshold": "Seuil (€)", "window_h": "Fenêtre (heures)", "min_count": "Nombre minimum d'opérations",
    "min_amount": "Montant minimum (€)", "max_amount": "Montant maximum (€)", "ratio": "Ratio débit / crédit",
    "band_low": "Borne basse (part du seuil)", "direction": "Sens (in = entrant, out = sortant)",
    "methods": "Moyens de paiement", "keywords": "Mots-clés", "credit_keywords": "Mots-clés du crédit",
    "absent_keywords": "Mots-clés qui doivent être absents", "channels": "Canaux", "factor": "Facteur (× médiane)",
    "min_tx": "Historique minimum (opérations)", "modulo": "Multiple (montants ronds)", "start": "Heure de début",
    "end": "Heure de fin", "dormant_days": "Jours d'inactivité", "early_days": "Jours après souscription",
    "max_days": "Durée de vie maximale (jours)", "min_ops": "Opérations minimum", "min_volume": "Volume minimum (€)",
    "min_counterparties": "Contreparties distinctes minimum", "min_countries": "Pays distincts minimum",
    "min_accounts": "Comptes distincts minimum", "min_bins": "BIN distincts minimum",
    "min_history": "Historique minimum (opérations)", "min_similarity": "Similarité minimale des noms (0-1)",
}


def param_input(code: str, key: str, value):
    label = f"{PARAM_LABELS.get(key, key)}  ·  {key}"
    widget_key = f"p_{code}_{key}"
    if isinstance(value, bool):
        return st.checkbox(label, value=value, key=widget_key)
    if isinstance(value, int):
        return int(st.number_input(label, value=value, step=1, key=widget_key))
    if isinstance(value, float):
        return float(st.number_input(label, value=value, step=0.05, format="%.2f", key=widget_key))
    if isinstance(value, list):
        raw = st.text_input(label + " (séparés par des virgules)", value=", ".join(map(str, value)), key=widget_key)
        items = [x.strip() for x in raw.split(",") if x.strip()]
        if value and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            try:
                return [float(x) if "." in x else int(x) for x in items]
            except ValueError:
                return value
        return items
    return st.text_input(label, value="" if value is None else str(value), key=widget_key)


def parse_list(text: str) -> list:
    items = [x.strip() for x in re.split(r"[,\n;]+", text) if x.strip()]
    return list(dict.fromkeys(items))


def parse_pairs(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s*[;:\-–]\s*", line, maxsplit=1)
        out[parts[0].upper()] = parts[1] if len(parts) > 1 else ""
    return out


def typology_rows(config: dict) -> pd.DataFrame:
    settings = cs.build_settings(config)
    active = {t.code for t in settings.typologies}
    return pd.DataFrame([{
        "Code": t.code, "Typologie": t.name, "Famille": t.family, "Actif": "Oui" if t.code in active else "Non",
        "Poids": t.weight,
    } for t in settings.all_typologies])


# ======================================================================== vue d'ensemble
with t_over:
    settings_d = cs.build_settings(draft)
    ui.kpis([
        ("Version publiée", f"v{published['version']}"),
        ("Typologies actives", f"{len(settings_d.typologies)} / {len(settings_d.all_typologies)}"),
        ("Seuils N1 / N2", f"{settings_d.n1} / {settings_d.n2}"),
        ("Clients en liste blanche", len(settings_d.whitelist_ids)),
    ])
    st.markdown(
        "**Circuit de modification recommandé** (bonnes pratiques de calibrage des dispositifs de surveillance) : "
        "1) modifier le brouillon · 2) **simuler** l'impact sur un jeu de données (alertes gagnées / perdues) · "
        "3) **publier** avec un motif obligatoire · 4) la modification est versionnée et tracée "
        "(avant / après, auteur, date), avec possibilité de **restaurer** une version antérieure.")
    st.caption(f"Dernière validation des listes de référence : {draft['lists'].get('reviewed')}")
    ui.section("Typologies (brouillon)")
    ui.show_table(typology_rows(draft), max_rows=120)

# ======================================================================== scores & seuils
with t_score:
    with st.form("form_thresholds"):
        st.markdown("**Niveaux de risque**")
        a, b = st.columns(2)
        n1 = a.number_input("Seuil N1 — alerte modérée (score ≥)", 1, 999, int(draft["thresholds"]["n1"]))
        n2 = b.number_input("Seuil N2 — escalade (score ≥)", 1, 1000, int(draft["thresholds"]["n2"]))
        c, d = st.columns(2)
        cap = c.number_input("Plafond du score", 1, 1000, int(draft["thresholds"]["cap"]))
        bonus = d.number_input("Bonus par typologie distincte supplémentaire (score client)", 0, 50,
                               int(draft["thresholds"]["diversity_bonus"]))
        st.markdown("**Opérations techniques exclues** (un mot par ligne ou séparés par des virgules)")
        excl = st.text_area("Mots exclus", value=", ".join(draft["exclusions"]), height=90,
                            label_visibility="collapsed")
        submit = st.form_submit_button("Enregistrer dans le brouillon")
    if submit:
        if not (0 < n1 < n2 <= cap):
            st.error("Il faut 0 < N1 < N2 ≤ plafond.")
        else:
            draft["thresholds"] = {"n1": int(n1), "n2": int(n2), "cap": int(cap), "diversity_bonus": int(bonus)}
            draft["exclusions"] = [x.upper() for x in parse_list(excl)]
            saved("Scores et seuils mis à jour")
    st.caption("Modèle à deux niveaux : N1 = revue documentaire, N2 = ouverture d'un dossier d'investigation. "
               "Pour mesurer l'effet d'un changement de seuil, utilisez l'onglet « Simulation ».")

# ======================================================================== typologies
with t_typo:
    settings_d = cs.build_settings(draft)
    labels = {t.code: f"{t.code} — {t.name}{'' if any(a.code == t.code for a in settings_d.typologies) else '  (désactivée)'}"
              for t in settings_d.all_typologies}
    family_filter = st.selectbox("Famille", ["Toutes"] + list(FAMILIES.values()), key="typo_family")
    codes = [t.code for t in settings_d.all_typologies if family_filter in ("Toutes", t.family)]
    if not codes:
        st.info("Aucune typologie dans cette famille.")
    else:
        code = st.selectbox("Typologie à modifier", codes, format_func=lambda c: labels[c], key="typo_pick")
        custom = next((c for c in draft["custom_typologies"] if c["code"] == code), None)
        entry = custom if custom else draft["typologies"][code]
        detector = custom["detector"] if custom else next(t.detector for t in TYPOLOGIES if t.code == code)
        st.caption(f"Détecteur : `{detector}` · colonnes requises : "
                   + ", ".join(["MONTANT"] + [COLUMN_LABELS.get(c, c) for c in DETECTOR_REQUIRES[detector]]))
        with st.form(f"form_typo_{code}"):
            enabled = st.checkbox("Typologie active", value=bool(entry.get("enabled", True)), key=f"en_{code}")
            name = st.text_input("Nom", value=entry["name"], key=f"nm_{code}")
            weight = st.slider("Poids (points ajoutés au score)", 0, 100, int(entry["weight"]), key=f"w_{code}")
            signal = st.text_area("Signal d'alerte (texte repris dans les constats)", value=entry.get("signal", ""),
                                  key=f"sg_{code}", height=80)
            st.markdown("**Paramètres**")
            new_params = {k: param_input(code, k, v) for k, v in entry["params"].items()}
            if not entry["params"]:
                st.caption("Cette typologie n'a pas de paramètre.")
            submit = st.form_submit_button("Enregistrer dans le brouillon")
        if submit:
            entry.update({"enabled": enabled, "name": name.strip() or entry["name"], "weight": int(weight),
                          "signal": signal.strip(), "params": new_params})
            saved(f"{code} mise à jour")
        b1, b2 = st.columns(2)
        with b1:
            if not custom and st.button("↩️ Revenir aux valeurs par défaut", key=f"reset_{code}"):
                draft["typologies"][code] = copy.deepcopy(cs.default_config()["typologies"][code])
                saved(f"{code} réinitialisée")
        with b2:
            if custom and st.button("🗑️ Supprimer cette typologie", key=f"del_{code}"):
                draft["custom_typologies"] = [c for c in draft["custom_typologies"] if c["code"] != code]
                saved(f"{code} supprimée")

    ui.section("Créer une typologie personnalisée")
    st.caption("Combinez un détecteur existant avec vos propres seuils, mots-clés et poids : aucune programmation requise.")
    examples = {}
    for t in TYPOLOGIES:
        examples.setdefault(t.detector, cs._jsonable(t.params))
    n1_, n2_ = st.columns(2)
    family_prefix = n1_.selectbox("Famille", list(FAMILIES), index=list(FAMILIES).index("CUS"),
                                  format_func=lambda p: f"{p} — {FAMILIES[p]}", key="new_family")
    used = {c for c in draft["typologies"]} | {c["code"] for c in draft["custom_typologies"]}
    suffix = next(i for i in range(1, 1000) if f"{family_prefix}-{i:02d}" not in used)
    new_code = n2_.text_input("Code", value=f"{family_prefix}-{suffix:02d}", key=f"new_code_{family_prefix}")
    new_name = st.text_input("Nom de la typologie", key="new_name")
    new_detector = st.selectbox("Détecteur", sorted(DETECTOR_REQUIRES), key="new_detector")
    st.caption("Colonnes requises : " + ", ".join(["MONTANT"] + [COLUMN_LABELS.get(c, c) for c in DETECTOR_REQUIRES[new_detector]]))
    new_params = st.text_area("Paramètres (JSON)", value=json.dumps(examples.get(new_detector, {}), ensure_ascii=False, indent=2),
                              height=140, key=f"new_params_{new_detector}")
    w1, w2 = st.columns([1, 3])
    new_weight = w1.number_input("Poids", 0, 100, 20, key="new_weight")
    new_signal = w2.text_input("Signal d'alerte", key="new_signal")
    if st.button("➕ Ajouter au brouillon", key="btn_add_typo"):
        try:
            params = json.loads(new_params)
            if not isinstance(params, dict):
                raise ValueError("Les paramètres doivent être un objet JSON { ... }.")
            candidate = copy.deepcopy(draft)
            candidate["custom_typologies"].append({
                "code": new_code.strip().upper(), "name": new_name.strip(), "weight": int(new_weight),
                "signal": new_signal.strip(), "detector": new_detector, "params": params, "enabled": True})
            problems = cs.validate_config(candidate) or cs.dry_run(candidate)
            if problems:
                st.error(" ; ".join(problems))
            else:
                draft["custom_typologies"] = candidate["custom_typologies"]
                saved(f"{new_code.strip().upper()} créée")
        except ValueError as exc:
            st.error(f"JSON invalide : {exc}")
    with st.expander("Détecteurs disponibles et exemples de paramètres"):
        ui.show_table(pd.DataFrame([{
            "Détecteur": d, "Colonnes requises": ", ".join(["MONTANT"] + [COLUMN_LABELS.get(c, c) for c in DETECTOR_REQUIRES[d]]),
            "Exemple de paramètres": json.dumps(examples.get(d, {}), ensure_ascii=False)} for d in sorted(DETECTOR_REQUIRES)]),
            max_rows=60)

# ======================================================================== listes de référence
with t_lists:
    lists = draft["lists"]
    with st.form("form_lists"):
        st.markdown("**Pays à haut risque** (une ligne `CODE;Nom`)")
        hr = st.text_area("hr", value="\n".join(f"{k};{v}" for k, v in lists["high_risk"].items()), height=170,
                          label_visibility="collapsed")
        st.markdown("**Territoires à fiscalité privilégiée** (une ligne `CODE;Nom`)")
        th = st.text_area("th", value="\n".join(f"{k};{v}" for k, v in lists["tax_havens"].items()), height=130,
                          label_visibility="collapsed")
        st.markdown("**Zone SEPA** (codes ISO2 séparés par des virgules)")
        sepa = st.text_area("sepa", value=", ".join(lists["sepa"]), height=80, label_visibility="collapsed")
        st.markdown("**Statuts KYC considérés comme défaillants**")
        kyc = st.text_area("kyc", value=", ".join(lists["kyc_failed"]), height=70, label_visibility="collapsed")
        reviewed = st.text_input("Dernière validation (qui, quand, source : GAFI / UE / OCDE)", value=str(lists.get("reviewed", "")))
        submit = st.form_submit_button("Enregistrer dans le brouillon")
    if submit:
        new_hr, new_th, new_sepa = parse_pairs(hr), parse_pairs(th), [c.upper() for c in parse_list(sepa)]
        bad = [c for c in list(new_hr) + list(new_th) + new_sepa if not re.fullmatch(r"[A-Z]{2}", c)]
        if bad:
            st.error("Codes pays invalides (ISO2 attendu) : " + ", ".join(bad))
        else:
            draft["lists"] = {"high_risk": new_hr, "tax_havens": new_th, "sepa": sorted(set(new_sepa)),
                              "kyc_failed": [x.upper() for x in parse_list(kyc)], "reviewed": reviewed.strip()}
            saved("Listes de référence mises à jour")
    st.caption("À revoir après chaque publication du GAFI (février, juin, octobre) et de la Commission européenne.")

# ======================================================================== liste blanche
with t_white:
    st.markdown("Les clients de cette liste ne génèrent **aucune alerte** (exemption justifiée, par exemple "
                "un client institutionnel dont l'activité a été validée). Chaque ajout exige un motif et est tracé.")
    ui.show_table(pd.DataFrame(draft["whitelist"], columns=["id", "reason", "added_at"]).rename(
        columns={"id": "ID client", "reason": "Motif", "added_at": "Ajouté le"}) if draft["whitelist"]
        else pd.DataFrame(), empty="Aucun client exempté.")
    with st.form("form_white"):
        w_id = st.text_input("ID client à exempter (tel qu'il figure dans la colonne ID_CLIENT)")
        w_reason = st.text_input("Motif de l'exemption (obligatoire)")
        add = st.form_submit_button("Ajouter au brouillon")
    if add:
        if not w_id.strip() or not w_reason.strip():
            st.error("L'ID client et le motif sont obligatoires.")
        elif any(w["id"] == w_id.strip() for w in draft["whitelist"]):
            st.error("Ce client est déjà exempté.")
        else:
            draft["whitelist"].append({"id": w_id.strip(), "reason": w_reason.strip(),
                                       "added_at": pd.Timestamp.now().strftime("%d/%m/%Y")})
            saved(f"Client {w_id.strip()} ajouté à la liste blanche")
    if draft["whitelist"]:
        remove = st.multiselect("Retirer de la liste blanche", [w["id"] for w in draft["whitelist"]])
        if remove and st.button("Retirer la sélection", key="btn_rm_white"):
            draft["whitelist"] = [w for w in draft["whitelist"] if w["id"] not in remove]
            saved("Liste blanche mise à jour")

# ======================================================================== import, contexte, apprentissage
with t_adv:
    st.markdown("### Fenêtre comportementale")
    with st.form("form_adv"):
        window = st.number_input("N dernières transactions examinées par client (0 = désactivée)", 0, 100,
                                 int(draft.get("window_n", 5)))
        st.markdown("### Liste blanche d'opérations récurrentes")
        wr = draft["whitelist_rules"]
        mode = st.radio("Condition d'exclusion", ["OR", "AND"], index=0 if wr.get("mode", "OR") == "OR" else 1,
                        horizontal=True, help="OR : un seul critère suffit. AND : tous les critères renseignés doivent correspondre.")
        w_labels = st.text_area("Libellés exclus (mots entiers)", ", ".join(wr.get("labels", [])), height=70)
        w_cp = st.text_area("Contreparties validées", ", ".join(wr.get("counterparties", [])), height=60)
        w_iban = st.text_area("IBAN validés", ", ".join(wr.get("ibans", [])), height=60)
        st.markdown("### Entités publiques (JSON : name, keywords, country)")
        pub_json = st.text_area("Entités publiques", json.dumps(draft["public_entities"], ensure_ascii=False, indent=1),
                                height=200)
        st.markdown("### Taux de change vers l'euro (JSON)")
        fx_json = st.text_input("Taux", json.dumps(draft.get("fx_rates", {})), help='Exemple : {"USD": 0.92, "GBP": 1.17}')
        st.markdown("### Synonymes d'en-têtes (JSON : champ standard → liste de noms)")
        syn_json = st.text_area("Synonymes", json.dumps(draft.get("header_synonyms", {}), ensure_ascii=False), height=80,
                                help='Exemple : {"MONTANT": ["Montant TTC", "Total facture"]}')
        st.markdown("### Contexte KYC / transaction")
        k1, k2, k3 = st.columns(3)
        ctx = draft["context"]
        b_high = k1.number_input("Bonus risque élevé (pts)", 0, 100, int(ctx.get("bonus_high", 10)))
        b_crit = k2.number_input("Bonus risque critique (pts)", 0, 100, int(ctx.get("bonus_critical", 20)))
        factor = k3.number_input("Facteur volume / volume KYC déclaré", 1.0, 100.0, float(ctx.get("kyc_volume_factor", 2.0)))
        learning = st.checkbox("Auto-enrichissement activé (historique clients et schémas de fraude)",
                               value=bool(draft["learning"].get("enabled", True)))
        ok = st.form_submit_button("Ajouter au brouillon")
    if ok:
        try:
            pub, fx, syn = json.loads(pub_json), json.loads(fx_json or "{}"), json.loads(syn_json or "{}")
            assert isinstance(pub, list) and all(isinstance(e, dict) and "name" in e and "keywords" in e for e in pub)
            assert isinstance(fx, dict) and isinstance(syn, dict)
        except (ValueError, AssertionError):
            st.error("JSON invalide : vérifiez la structure des entités publiques, des taux ou des synonymes.")
        else:
            draft["window_n"] = int(window)
            draft["whitelist_rules"] = {"mode": mode, "labels": [x.upper() for x in parse_list(w_labels)],
                                        "counterparties": parse_list(w_cp), "ibans": [x.replace(" ", "").upper() for x in parse_list(w_iban)]}
            draft["public_entities"], draft["fx_rates"], draft["header_synonyms"] = pub, fx, syn
            draft["context"] = {"bonus_high": int(b_high), "bonus_critical": int(b_crit), "kyc_volume_factor": float(factor)}
            draft["learning"] = {"enabled": bool(learning)}
            saved("Paramètres avancés mis à jour")

    st.markdown("### Référentiel des secteurs (sectors_reference.csv)")
    sectors = enrichment.load_sectors()
    edited = st.data_editor(sectors, num_rows="dynamic", key="sectors_editor", width="stretch",
                            column_config={"Risk_Level": st.column_config.SelectboxColumn(options=enrichment.RISK_LEVELS)})
    if st.button("💾 Enregistrer le référentiel des secteurs", key="btn_save_sectors"):
        enrichment.save_csv(enrichment.SECTORS_FILE, edited.dropna(how="all"))
        st.success("Référentiel enregistré (pensez à le versionner dans GitHub : le disque Streamlit Cloud est éphémère).")

    st.markdown("### Fichiers d'auto-enrichissement")
    for label, name, cols in (("Historique des profils clients", enrichment.PROFILES_FILE, enrichment.PROFILE_COLS),
                              ("Schémas de fraude appris", enrichment.PATTERNS_FILE, enrichment.PATTERN_COLS)):
        frame = enrichment.load_csv(name, cols)
        st.markdown(f"**{label}** — {len(frame)} ligne(s)")
        ui.show_table(frame.tail(10), max_rows=10, empty="Aucune analyse validée pour le moment.")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(f"⬇️ Télécharger {name}", frame.to_csv(index=False).encode("utf-8"), file_name=name,
                               mime="text/csv", key=f"dl_{name}")
        with d2:
            if st.button(f"🗑️ Vider {name}", key=f"clr_{name}"):
                enrichment.save_csv(name, frame.iloc[0:0])
                st.rerun()
    st.markdown("### Export de la configuration")
    st.download_button("⬇️ Télécharger config_rules.json (version publiée)",
                       json.dumps(published, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name="config_rules.json", mime="application/json", key="dl_cfg")
    st.caption("Streamlit Cloud ayant un disque éphémère, déposez ce fichier et les CSV dans GitHub pour les conserver.")

# ======================================================================== simulation (ATL / BTL)
with t_sim:
    st.markdown("Comparez la **version publiée** et le **brouillon** sur le même jeu de données : alertes gagnées "
                "(*below-the-line*) et alertes perdues (*above-the-line*) avant toute publication.")
    source_kind = st.radio("Jeu de données", ["Données de démonstration", "Mon fichier (Excel / CSV)"], horizontal=True)
    upload = st.file_uploader("Fichier de test", type=["csv", "xlsx", "xls"], key="sim_file") \
        if source_kind.startswith("Mon") else None
    if st.button("▶️ Lancer la simulation", key="btn_sim"):
        if source_kind.startswith("Mon") and upload is None:
            st.warning("Chargez un fichier pour la simulation.")
        else:
            try:
                with st.spinner("Simulation en cours…"):
                    raw = demo_dataframe() if upload is None else load_file(upload)
                    raw = raw.copy()
                    raw["LIGNE"] = range(2, len(raw) + 2)
                    s_pub, s_dr = cs.build_settings(cs.load_config()), cs.build_settings(draft)
                    r_pub = run_analysis(normalize(raw, s_pub.exclusions)[0], s_pub)
                    r_dr = run_analysis(normalize(raw, s_dr.exclusions)[0], s_dr)
                    st.session_state["sim"] = (r_pub, r_dr)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Simulation impossible : {exc}")
    if "sim" in st.session_state:
        r_pub, r_dr = st.session_state["sim"]
        a, b = r_pub.df, r_dr.df

        def summary(r):
            d = r.df
            flagged = d[d["NB_TYPOLOGIES"] > 0]
            return {"suspectes": len(flagged), "n2": int((d["NIVEAU"] == cfg.LEVEL_N2).sum()),
                    "n1": int((d["NIVEAU"] == cfg.LEVEL_N1).sum()), "volume": float(flagged["MONTANT"].sum())}

        sp, sd = summary(r_pub), summary(r_dr)
        ui.kpis([("Opérations suspectes", f"{sp['suspectes']} → {sd['suspectes']}"),
                 ("Escalade N2", f"{sp['n2']} → {sd['n2']}"), ("Niveau N1", f"{sp['n1']} → {sd['n1']}"),
                 ("Volume signalé", f"{ui.fmt_eur(sp['volume'])} → {ui.fmt_eur(sd['volume'])}")])
        by_code = pd.DataFrame({
            "Code": list(r_dr.typology_status["Code"]),
            "Typologie": list(r_dr.typology_status["Typologie"]),
        })
        pub_counts = dict(zip(r_pub.typology_status["Code"], r_pub.typology_status["Alertes"]))
        by_code["Alertes publiées"] = by_code["Code"].map(lambda c: int(pub_counts.get(c, 0)))
        by_code["Alertes brouillon"] = list(r_dr.typology_status["Alertes"].astype(int))
        by_code["Écart"] = by_code["Alertes brouillon"] - by_code["Alertes publiées"]
        ui.section("Impact par typologie")
        ui.show_table(by_code[(by_code["Écart"] != 0) | (by_code["Alertes brouillon"] > 0)]
                      .sort_values("Écart", key=abs, ascending=False), max_rows=100)
        keep = ["LIGNE", "ID_CLIENT", "MONTANT", "RISK_SCORE", "NIVEAU", "NB_TYPOLOGIES"]
        merged = a[[c for c in keep if c in a.columns]].merge(
            b[[c for c in keep + ["ALERTES"] if c in b.columns]], on="LIGNE", how="outer", suffixes=(" (publié)", " (brouillon)"))
        flag_pub = merged["NB_TYPOLOGIES (publié)"].fillna(0) > 0
        flag_dr = merged["NB_TYPOLOGIES (brouillon)"].fillna(0) > 0
        cols = ["LIGNE", "ID_CLIENT (brouillon)", "MONTANT (brouillon)", "RISK_SCORE (publié)", "RISK_SCORE (brouillon)",
                "NIVEAU (publié)", "NIVEAU (brouillon)"]
        cols = [c for c in cols if c in merged.columns]
        gained = merged[flag_dr & ~flag_pub][cols].rename(columns=lambda c: c.replace(" (brouillon)", "") if "ID_CLIENT" in c or "MONTANT" in c else c)
        lost = merged[flag_pub & ~flag_dr][cols].rename(columns=lambda c: c.replace(" (brouillon)", "") if "ID_CLIENT" in c or "MONTANT" in c else c)
        ui.section(f"Alertes gagnées — below-the-line ({len(gained)})")
        ui.show_table(gained, empty="Aucune alerte supplémentaire.", max_rows=100)
        ui.section(f"Alertes perdues — above-the-line ({len(lost)})")
        ui.show_table(lost, empty="Aucune alerte supprimée.", max_rows=100)
        st.download_button("📊 Exporter la simulation (Excel)", key="dl_sim",
                           data=to_excel_bytes({"Par typologie": by_code, "Alertes gagnées": gained, "Alertes perdues": lost}),
                           file_name="argus_simulation_parametrage.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("Conservez cet export comme preuve de test : échantillonnez les alertes gagnées et perdues avant de publier.")

# ======================================================================== publication & historique
with t_pub:
    ui.section("Modifications en attente")
    ui.show_table(pd.DataFrame(changes), empty="Aucune modification en attente.", max_rows=200)
    problems = cs.validate_config(draft)
    if changes and not problems:
        problems = cs.dry_run(draft)
    for p in problems:
        st.error(p)
    if changes:
        with st.form("form_publish"):
            author = st.text_input("Auteur", value="Head of Compliance")
            reason = st.text_area("Motif de la modification (obligatoire : sera inscrit dans l'historique)", height=90)
            tested = st.checkbox("J'ai mesuré l'impact (onglet Simulation) et j'approuve cette modification")
            go = st.form_submit_button("🚀 Publier la configuration")
        if go:
            if not tested:
                st.error("Confirmez que l'impact a été mesuré et approuvé.")
            elif problems:
                st.error("Corrigez les erreurs avant de publier.")
            else:
                try:
                    new = cs.publish(draft, author, reason)
                    st.session_state["draft"] = copy.deepcopy(new)
                    st.session_state["flash"] = f"Configuration v{new['version']} publiée et tracée."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        if st.button("↩️ Abandonner le brouillon", key="btn_discard"):
            st.session_state["draft"] = copy.deepcopy(published)
            st.rerun()

    ui.section("Export / import")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button("⬇️ Exporter la configuration publiée (rules.json)", key="dl_rules",
                           data=json.dumps(published, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="rules.json", mime="application/json")
    with e2:
        imported = st.file_uploader("Importer une configuration (rules.json) dans le brouillon", type=["json"], key="imp_rules")
        if imported is not None and st.button("Charger dans le brouillon", key="btn_import"):
            try:
                st.session_state["draft"] = cs._merge(cs.default_config(), json.loads(imported.getvalue().decode("utf-8")))
                st.session_state["flash"] = "Configuration importée dans le brouillon"
                st.rerun()
            except ValueError:
                st.error("Fichier JSON illisible.")
    st.info("Sur Streamlit Cloud, le disque est réinitialisé à chaque redéploiement : après publication, exportez "
            "`rules.json` et déposez-le dans le dossier `config/` du dépôt GitHub pour le rendre permanent.")

    ui.section("Historique et traçabilité")
    audit = cs.read_audit()
    if not audit:
        st.caption("Aucune publication enregistrée.")
    else:
        ui.show_table(pd.DataFrame([{"Version": f"v{r['version']}", "Date": r["at"], "Auteur": r["by"],
                                     "Motif": r["reason"], "Modifications": len(r["changes"])}
                                    for r in reversed(audit)]), max_rows=100)
        picked = st.selectbox("Détail d'une version", [r["version"] for r in reversed(audit)],
                              format_func=lambda v: f"v{v}", key="hist_pick")
        record = next(r for r in audit if r["version"] == picked)
        ui.show_table(pd.DataFrame(record["changes"]), empty="Aucun détail.", max_rows=200)
        if st.button("⏪ Restaurer cette version dans le brouillon", key="btn_restore"):
            snap = next((h for h in cs.read_history() if h["version"] == picked), None)
            if snap:
                st.session_state["draft"] = cs._merge(cs.default_config(), snap["config"])
                st.session_state["flash"] = f"Version v{picked} restaurée dans le brouillon"
                st.rerun()
        st.download_button("⬇️ Exporter le journal d'audit", key="dl_audit",
                           data=json.dumps(audit, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="audit_log.json", mime="application/json")
