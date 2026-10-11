"""Argus RISK — point d'entrée (menu latéral et navigation entre les pages).

Lancer :  streamlit run main.py
"""

import streamlit as st

from core import config as cfg
from core import ui

st.set_page_config(
    page_title=cfg.APP_TITLE,
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui.inject_css()
ui.sidebar_brand()

navigation = st.navigation(
    [
        st.Page("views/home.py", title="Accueil", icon="🏠", default=True),
        st.Page("views/import_data.py", title="Import de données", icon="📥", url_path="import"),
        st.Page("views/kyc_input.py", title="Contexte KYC", icon="🧾", url_path="kyc"),
        st.Page("views/analysis.py", title="Alertes & analyse", icon="🚨", url_path="analyse"),
        st.Page("views/typologies.py", title="Moteur de règles", icon="🔎", url_path="regles"),
        st.Page("views/guide.py", title="Guide d'utilisation", icon="📘", url_path="guide"),
        st.Page("views/admin.py", title="Paramètres (Admin)", icon="⚙️", url_path="admin"),
    ],
)
navigation.run()
ui.footer()
