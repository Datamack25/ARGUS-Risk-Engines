"""Page Guide : utilisation, format des données, mise à jour, dépannage."""

import streamlit as st

from core import config as cfg
from core import ui
from core.guide import SECTIONS

ui.banner("Guide d'utilisation & de mise à jour", f"{cfg.APP_NAME} — version {cfg.VERSION}", compact=True)
_, left, _ = st.columns([1, 1, 1])
with left:
    ui.go_button("← Accueil", "views/home.py", "btn_back_guide")

with st.container(key="card_guide"):
    tabs = st.tabs(list(SECTIONS))
    for tab, markdown in zip(tabs, SECTIONS.values()):
        with tab:
            st.markdown(markdown)
