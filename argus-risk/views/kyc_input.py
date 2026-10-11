"""Page Contexte KYC : informations client par secteur et contexte de la transaction."""

import streamlit as st

from core import config as cfg
from core import enrichment, ui
from core.reference_lists import NAME_TO_ISO2

ui.banner("Contexte KYC & transaction", "Ces informations majorent le score des opérations déjà alertées", compact=True)

SECTORS = {
    "Banque": ["Type de compte", "Revenus mensuels déclarés (€)", "Origine des fonds"],
    "Assurance": ["Type de contrat", "Prime annuelle (€)", "Bénéficiaire désigné"],
    "Jeux en ligne": ["Pseudo / ID joueur", "Mise mensuelle habituelle (€)", "Interdit de jeu (ANJ)"],
    "Paiement / FinTech": ["Type de compte marchand", "Volume mensuel attendu (€)", "Activité du marchand"],
    "Crypto-actifs": ["Plateforme", "Adresse de portefeuille déclarée", "Source des fonds"],
}
PAYMENTS = ["Virement SEPA", "Virement international", "Carte bancaire", "Espèces", "Chèque", "Prélèvement",
            "Crypto-actifs", "Mandat / transfert d'argent", "Autre"]
CTYPES = ["Personne morale résidente", "Personne physique résidente", "Personne physique non résidente",
          "Société offshore / écran", "Entité publique", "Association", "Autre"]
countries = sorted(NAME_TO_ISO2) if isinstance(NAME_TO_ISO2, dict) else []
ctx = st.session_state.get("context", {"kyc": {}, "transaction": {}})

with st.form("kyc_form"):
    st.markdown("### Fiche KYC")
    c1, c2 = st.columns(2)
    sector = c1.selectbox("Secteur d'activité du client", list(SECTORS),
                          index=list(SECTORS).index(ctx["kyc"].get("secteur", "Banque")))
    ppe = c2.checkbox("Client déclaré PPE (personne politiquement exposée)", value=ctx["kyc"].get("ppe", False))
    f1, f2, f3 = st.columns(3)
    fields = SECTORS[sector]
    answers = {fields[0]: f1.text_input(fields[0], value=ctx["kyc"].get("champs", {}).get(fields[0], "")),
               fields[1]: f2.text_input(fields[1], value=ctx["kyc"].get("champs", {}).get(fields[1], "")),
               fields[2]: f3.text_input(fields[2], value=ctx["kyc"].get("champs", {}).get(fields[2], ""))}
    volume = st.number_input("Volume annuel déclaré au KYC (€) — 0 = non renseigné", min_value=0.0, step=1000.0,
                             value=float(ctx["kyc"].get("volume_annuel_declare", 0.0)))

    st.markdown("### Contexte de la transaction")
    t1, t2 = st.columns(2)
    origin = t1.text_input("Pays d'origine des fonds", value=ctx["transaction"].get("pays_origine", ""))
    dest = t2.text_input("Pays de destination", value=ctx["transaction"].get("pays_destination", ""))
    t3, t4 = st.columns(2)
    pay = t3.selectbox("Moyen de paiement", PAYMENTS,
                       index=PAYMENTS.index(ctx["transaction"].get("moyen_paiement", PAYMENTS[0])))
    ctype = t4.selectbox("Type de contrepartie", CTYPES,
                         index=CTYPES.index(ctx["transaction"].get("type_contrepartie", CTYPES[0])))
    sectors = enrichment.load_sectors()
    options = [""] + list(sectors["Sector_Name"])
    current = ctx["transaction"].get("secteur_contrepartie", "")
    csector = st.selectbox("Secteur de la contrepartie", options, index=options.index(current) if current in options else 0)
    effect = st.text_area("Effet générateur (origine économique ou fait générateur de l'opération)",
                          value=ctx["transaction"].get("effet_generateur", ""), height=80,
                          placeholder="Ex. : vente d'un bien immobilier, versement d'héritage, facture de prestation…")
    submitted = st.form_submit_button("Enregistrer le contexte")

if submitted:
    st.session_state["context"] = {
        "kyc": {"secteur": sector, "ppe": ppe, "champs": answers, "volume_annuel_declare": volume},
        "transaction": {"pays_origine": origin.strip(), "pays_destination": dest.strip(), "moyen_paiement": pay,
                        "type_contrepartie": ctype, "secteur_contrepartie": csector,
                        "effet_generateur": effect.strip()},
    }
    st.session_state.pop("result", None)
    st.success("Contexte enregistré : il sera pris en compte à la prochaine analyse.")

st.caption("Le contexte est facultatif. Il ne crée pas d'alerte : il majore les opérations déjà alertées "
           "(barèmes réglables dans Paramètres › Contexte).")
_, a, b, _ = st.columns([1, 2, 2, 1])
with a:
    ui.go_button("📥 Import de données", "views/import_data.py", "btn_kyc_import")
with b:
    ui.go_button("🚨 Voir l'analyse", "views/analysis.py", "btn_kyc_analysis")
