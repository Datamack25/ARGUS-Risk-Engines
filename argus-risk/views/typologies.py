"""Page Typologies : catalogue des typologies appliquées par le moteur."""

import pandas as pd
import streamlit as st

from core import config as cfg
from core import ui
from core.settings import load_settings
from core.typologies import COLUMN_LABELS, FAMILIES, required_columns

settings = load_settings()
TYPOLOGIES = settings.typologies

ui.banner(f"Les {len(TYPOLOGIES)} typologies actives", "Fraude, blanchiment, LCB-FT, fiscalité, travail illégal", compact=True)
_, left, _ = st.columns([1, 1, 1])
with left:
    ui.go_button("← Accueil", "views/home.py", "btn_back_typo")

st.markdown(
    f'<div class="hero-desc">Le score d\'une opération est la somme des poids des typologies déclenchées '
    f"(plafond {settings.cap}). Seuils : N1 ≥ {settings.n1}, escalade N2 ≥ {settings.n2}.</div>",
    unsafe_allow_html=True)

families = sorted({t.family for t in TYPOLOGIES}, key=list(FAMILIES.values()).index)
chosen = st.multiselect("Familles", families, default=families)
catalogue = pd.DataFrame([{
    "Code": t.code, "Typologie": t.name, "Famille": t.family, "Poids": t.weight,
    "Signal d'alerte": t.signal,
    "Colonnes requises": ", ".join(["MONTANT"] + [COLUMN_LABELS.get(c, c) for c in required_columns(t)]),
} for t in TYPOLOGIES])
ui.show_table(catalogue[catalogue["Famille"].isin(chosen)], max_rows=100)
