"""Composants d'interface : styles, bandeau, cartes, tableaux, pied de page.

Les couleurs sont imposées explicitement (texte foncé sur fond clair, boutons bleus à texte blanc)
afin que l'affichage soit identique quel que soit le thème (clair ou sombre) du navigateur.
"""

import html
from datetime import datetime

import pandas as pd
import streamlit as st

from . import config as cfg
from .settings import load_settings

NAVY, BLUE, BLUE_DARK, TEXT, MUTED = "#0d2a52", "#1e5aa8", "#163f78", "#1e293b", "#64748b"

CSS = f"""
<style>
:root {{ color-scheme: light; }}
.stApp {{ background: #f4f6f9; color: {TEXT}; }}
#MainMenu, footer, [data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"], .stAppDeployButton, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stToolbar"] {{ background: transparent !important; }}
header[data-testid="stHeader"] {{ background: transparent !important; }}
/* Boutons d'ouverture / fermeture du menu : bleus, icône blanche (toujours visibles) */
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button, [data-testid="stSidebarCollapseButton"] button {{
    background: {BLUE} !important; border-radius: 8px !important; opacity: 1 !important;
}}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapsedControl"] *, [data-testid="stSidebarCollapseButton"] * {{
    color: #ffffff !important; fill: #ffffff !important;
}}
[data-testid="stMainBlockContainer"], .block-container {{
    max-width: 1180px; margin: 0 auto; padding: 1.2rem 1.5rem 2rem 1.5rem;
}}

/* Texte : foncé partout, quel que soit le thème */
.stApp [data-testid="stMarkdownContainer"] :where(p, li, span, strong, em, h1, h2, h3, h4, h5, h6, a, td, th) {{ color: {TEXT} !important; }}
.stApp [data-testid="stWidgetLabel"] *, .stApp label *, .stApp [data-testid="stCaptionContainer"] * {{ color: {TEXT} !important; }}
.stApp [data-testid="stCaptionContainer"] * {{ color: {MUTED} !important; }}


/* Code (en ligne et blocs) : texte blanc sur fond sombre */
.stApp [data-testid="stMarkdownContainer"] code {{
    background: #1e293b !important; color: #ffffff !important; border-radius: 6px; padding: .1rem .4rem;
}}
.stApp [data-testid="stCode"], .stApp [data-testid="stCodeBlock"], .stApp pre {{ background: #1e293b !important; border-radius: 10px; }}
.stApp [data-testid="stMarkdownContainer"] pre code {{ background: transparent !important; padding: 0; }}
.stApp pre, .stApp pre code, .stApp pre code *, .stApp [data-testid="stCode"] *, .stApp [data-testid="stCodeBlock"] * {{
    color: #f8fafc !important;
}}
.stApp [data-testid="stCodeBlock"] button svg, .stApp [data-testid="stCode"] button svg {{ fill: #f8fafc !important; color: #f8fafc !important; }}

/* Bandeau */
.header-banner {{
    background: linear-gradient(180deg, {NAVY} 0%, #1a4e8c 100%); border-radius: 16px;
    padding: 2.6rem 1rem 2.1rem 1rem; text-align: center; margin: .6rem 0 1.8rem 0;
    box-shadow: 0 6px 20px rgba(13,42,82,.18);
}}
.header-banner.compact {{ padding: 1.4rem 1rem 1.2rem 1rem; margin-bottom: 1.2rem; }}
.stApp .header-banner * {{ color: #ffffff !important; }}
.header-title {{ font-size: 2.5rem; font-weight: 700; letter-spacing: .5px; margin-bottom: .5rem; }}
.header-banner.compact .header-title {{ font-size: 1.7rem; margin-bottom: .3rem; }}
.header-line {{ width: 220px; height: 2px; background: rgba(255,255,255,.45); margin: 0 auto .9rem auto; }}
.header-banner.compact .header-line {{ display: none; }}
.header-subtitle {{ font-size: 1.02rem; font-weight: 300; opacity: .92; }}

/* Textes centrés */
.hero-title {{ text-align: center; font-size: 1.9rem; font-weight: 700; margin: .4rem 0 .3rem 0; }}
.hero-desc {{ text-align: center; color: {MUTED}; font-size: 1rem; margin-bottom: 1.4rem; }}
.stApp .hero-title {{ color: {TEXT} !important; }}
.stApp .hero-desc {{ color: {MUTED} !important; }}
.sec-title {{ font-size: 1.25rem; font-weight: 700; margin: 1.6rem 0 .6rem 0; text-align: center; }}
.stApp .sec-title {{ color: {NAVY} !important; }}
.status-line {{ text-align: center; font-size: .92rem; margin: .5rem 0 .8rem 0; font-style: italic; }}
.stApp .status-line {{ color: {BLUE} !important; }}

/* Cartes */
.st-key-upload_card, .st-key-card_findings, .st-key-card_guide {{
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 1.6rem 1.8rem;
    box-shadow: 0 4px 20px rgba(0,0,0,.05);
}}
.st-key-upload_card {{ max-width: 100%; margin: 0 auto 1rem auto; }}

/* Boutons : bleus, texte blanc, centrés */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button, [data-testid="stFileUploader"] button {{
    background-color: {BLUE} !important; border: none !important; border-radius: 10px !important;
    min-height: 48px; padding: .6rem 1.2rem !important; font-weight: 600 !important;
    box-shadow: 0 3px 8px rgba(30,90,168,.25) !important; transition: all .2s ease !important;
}}
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {{ width: 100% !important; }}
.stButton button:hover, .stDownloadButton button:hover, [data-testid="stFormSubmitButton"] button:hover, [data-testid="stFileUploader"] button:hover {{
    background-color: {BLUE_DARK} !important; transform: translateY(-2px);
}}
.stButton button:disabled {{ background-color: #94a3b8 !important; box-shadow: none !important; transform: none; }}
.stApp .stButton button *, .stApp .stDownloadButton button *, .stApp [data-testid="stFormSubmitButton"] button *, .stApp [data-testid="stFileUploader"] button * {{
    color: #ffffff !important; fill: #ffffff !important;
}}
.stButton, .stDownloadButton, [data-testid="stButton"], [data-testid="stDownloadButton"] {{ text-align: center; width: 100% !important; }}
.stButton > button, .stDownloadButton > button {{ width: 100% !important; }}
[data-testid="stElementContainer"]:has(> .stButton), [data-testid="stElementContainer"]:has(> .stDownloadButton), .stElementContainer:has(> .stButton), .stElementContainer:has(> .stDownloadButton) {{ width: 100% !important; }}

/* Champs numériques et formulaires */
.stApp [data-testid="stNumberInput"] button {{ background: #e2e8f0 !important; min-height: 0; box-shadow: none !important; }}
.stApp [data-testid="stNumberInput"] button * {{ color: {NAVY} !important; fill: {NAVY} !important; }}
[data-testid="stForm"] {{ background: #ffffff; border: 1px solid #e2e8f0 !important; border-radius: 12px; }}
.stApp [data-testid="stExpander"] summary * {{ color: {TEXT} !important; }}

/* Import de fichier */
[data-testid="stFileUploaderDropzone"] {{
    background: #f8fafc !important; border: 1.5px dashed {NAVY} !important; border-radius: 12px !important;
}}
.stApp [data-testid="stFileUploaderDropzone"] :where(span, small, p, div) {{ color: {TEXT} !important; }}
.stApp [data-testid="stFileUploaderDropzone"] button * {{ color: #ffffff !important; }}
.stApp [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] * {{ color: {TEXT} !important; }}

/* Champs de saisie */
.stApp div[data-baseweb="select"] > div, .stApp div[data-baseweb="input"], .stApp input, .stApp textarea {{
    background-color: #ffffff !important; color: {TEXT} !important; border-color: #cbd5e1 !important;
}}
.stApp div[data-baseweb="select"] * {{ color: {TEXT} !important; }}
.stApp [data-baseweb="tag"] {{ background-color: {BLUE} !important; }}
.stApp [data-baseweb="tag"] * {{ color: #ffffff !important; }}
[data-baseweb="popover"], [data-baseweb="popover"] ul, [data-baseweb="menu"] {{ background-color: #ffffff !important; }}
[data-baseweb="popover"] li, [data-baseweb="popover"] li * {{ color: {TEXT} !important; }}

/* Onglets */
.stTabs [data-baseweb="tab-list"] {{ gap: 10px; justify-content: center; flex-wrap: wrap; border-bottom: none !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
.stTabs [data-baseweb="tab"] {{ background: #e2e8f0; border-radius: 10px; height: 44px; padding: 8px 18px; }}
.stApp .stTabs [data-baseweb="tab"] p {{ color: #334155 !important; font-weight: 600; }}
.stApp .stTabs [aria-selected="true"] {{ background: {NAVY} !important; }}
.stApp .stTabs [aria-selected="true"] p {{ color: #ffffff !important; }}

/* Indicateurs */
.kpis {{ display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; margin: 1rem 0 .4rem 0; }}
.kpi {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: .9rem 1.2rem; min-width: 140px; flex: 1; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,.04); }}
.kpi-v {{ font-size: 1.5rem; font-weight: 700; }}
.kpi-l {{ font-size: .82rem; margin-top: .15rem; }}
.stApp .kpi-v {{ color: {NAVY} !important; }}
.stApp .kpi-l {{ color: {MUTED} !important; }}

/* Verdict */
.verdict {{ border-radius: 12px; padding: 1rem 1.3rem; font-weight: 600; text-align: center; font-size: 1.05rem; }}
.verdict.v-n2 {{ background: #fee2e2; border: 1px solid #fca5a5; }}
.verdict.v-n1 {{ background: #fef3c7; border: 1px solid #fcd34d; }}
.verdict.v-ok {{ background: #dcfce7; border: 1px solid #86efac; }}
.stApp .verdict.v-n2 {{ color: #991b1b !important; }}
.stApp .verdict.v-n1 {{ color: #92400e !important; }}
.stApp .verdict.v-ok {{ color: #166534 !important; }}

/* Tableaux */
.tbl-wrap {{ max-height: 460px; overflow: auto; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; margin: .4rem 0 1rem 0; }}
table.argus {{ border-collapse: collapse; width: 100%; font-size: .82rem; }}
table.argus th {{ position: sticky; top: 0; background: {NAVY}; text-align: left; padding: .55rem .7rem; white-space: nowrap; }}
.stApp table.argus th {{ color: #ffffff !important; }}
table.argus td {{ padding: .5rem .7rem; border-top: 1px solid #eef2f7; vertical-align: top; background: #fff; }}
table.argus tr:nth-child(even) td {{ background: #f8fafc; }}
.stApp table.argus td {{ color: {TEXT} !important; }}
table.argus td.num {{ text-align: right; white-space: nowrap; }}
table.argus td.wrap {{ min-width: 280px; }}
.badge {{ display: inline-block; border-radius: 20px; padding: .1rem .6rem; font-weight: 700; font-size: .78rem; white-space: nowrap; }}
.b-low {{ background: #dcfce7; }} .b-n1 {{ background: #fef3c7; }} .b-n2 {{ background: #fee2e2; }}
.stApp .b-low {{ color: #166534 !important; }} .stApp .b-n1 {{ color: #92400e !important; }} .stApp .b-n2 {{ color: #991b1b !important; }}
.tbl-note {{ text-align: center; font-size: .85rem; }}
.stApp .tbl-note {{ color: {MUTED} !important; }}

/* Histogrammes */
.bars {{ margin: .4rem 0 1rem 0; }}
.bar-row {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; }}
.bar-l {{ flex: 0 0 38%; font-size: .85rem; text-align: right; }}
.bar-t {{ flex: 1; background: #e2e8f0; border-radius: 8px; height: 16px; overflow: hidden; }}
.bar-f {{ background: {BLUE}; height: 100%; border-radius: 8px; }}
.bar-v {{ flex: 0 0 52px; font-size: .85rem; font-weight: 700; }}
.stApp .bar-l, .stApp .bar-v {{ color: {TEXT} !important; }}

/* Pied de page */
.app-footer {{ text-align: center; margin: 2.5rem 0 .5rem 0; padding-top: 1.2rem; border-top: 1px solid #dbe3ee; font-size: .85rem; line-height: 1.6; }}
.stApp .app-footer, .stApp .app-footer * {{ color: {MUTED} !important; }}
.stApp .app-footer strong {{ color: {NAVY} !important; }}

/* Menu latéral (style tableau de bord) */
[data-testid="stSidebar"] {{ background: {NAVY} !important; }}
[data-testid="stSidebar"] > div:first-child {{ background: {NAVY} !important; }}
.stApp [data-testid="stSidebar"] *, .stApp [data-testid="stSidebarNav"] * {{ color: #e2e8f0 !important; }}
[data-testid="stSidebarNav"] a {{ border-radius: 8px; margin: 2px 8px; padding: .35rem .6rem; }}
[data-testid="stSidebarNav"] a:hover {{ background: rgba(255,255,255,.12) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: {BLUE} !important; }}
.stApp [data-testid="stSidebarNav"] a[aria-current="page"] * {{ color: #ffffff !important; font-weight: 700; }}
[data-testid="stSidebarCollapseButton"] svg, [data-testid="stSidebarCollapsedControl"] svg {{ fill: #ffffff !important; color: #ffffff !important; }}
.side-brand {{ padding: 1rem .8rem .4rem .8rem; font-size: 1.3rem; font-weight: 800; letter-spacing: .5px; }}
.side-sub {{ padding: 0 .8rem 1rem .8rem; font-size: .75rem; opacity: .8; }}

/* Cartes de tableau de bord */
.dcard {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.1rem 1.3rem; box-shadow: 0 2px 12px rgba(0,0,0,.05); margin-bottom: 1rem; }}
.dcard-t {{ font-weight: 700; font-size: 1.02rem; margin-bottom: .7rem; }}
.stApp .dcard-t {{ color: {NAVY} !important; }}
.stApp .dcard, .stApp .dcard * {{ color: {TEXT}; }}
.stApp .dcard .dcard-t {{ color: {NAVY} !important; }}
.dcard-muted {{ font-size: .82rem; }}
.stApp .dcard .dcard-muted {{ color: {MUTED} !important; }}
.wl-badge {{ display: inline-block; margin: 3px 4px 3px 0; padding: .25rem .7rem; border-radius: 20px; font-size: .8rem; font-weight: 600; background: #dcfce7; border: 1px solid #86efac; }}
.stApp .dcard .wl-badge {{ color: #166534 !important; }}
.crit-badge {{ display: inline-block; padding: .15rem .6rem; border-radius: 20px; font-size: .78rem; font-weight: 700; background: #fee2e2; }}
.stApp .dcard .crit-badge {{ color: #991b1b !important; }}
.mod-badge {{ display: inline-block; padding: .15rem .6rem; border-radius: 20px; font-size: .78rem; font-weight: 700; background: #ffedd5; }}
.stApp .dcard .mod-badge {{ color: #9a3412 !important; }}
table.map {{ border-collapse: collapse; width: 100%; font-size: .85rem; }}
table.map th {{ text-align: left; padding: .45rem .6rem; background: {NAVY}; }}
.stApp table.map th {{ color: #ffffff !important; }}
table.map td {{ padding: .22rem .6rem; border-top: 1px solid #eef2f7; white-space: nowrap; }}
.m-ok {{ color: #166534; font-weight: 700; }} .m-fz {{ color: #9a3412; font-weight: 700; }} .m-no {{ color: #991b1b; font-weight: 700; }}
.stApp table.map .m-ok {{ color: #166534 !important; }} .stApp table.map .m-fz {{ color: #9a3412 !important; }} .stApp table.map .m-no {{ color: #991b1b !important; }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def banner(title: str, subtitle: str = "", compact: bool = False):
    cls = "header-banner compact" if compact else "header-banner"
    st.markdown(f'<div class="{cls}"><div class="header-title">{html.escape(title)}</div>'
                f'<div class="header-line"></div><div class="header-subtitle">{html.escape(subtitle)}</div></div>',
                unsafe_allow_html=True)


def section(title: str):
    st.markdown(f'<div class="sec-title">{html.escape(title)}</div>', unsafe_allow_html=True)


def kpis(items):
    cells = "".join(f'<div class="kpi"><div class="kpi-v">{html.escape(str(v))}</div>'
                    f'<div class="kpi-l">{html.escape(l)}</div></div>' for l, v in items)
    st.html(f'<div class="kpis">{cells}</div>')


def verdict(kind: str, text: str):
    st.html(f'<div class="verdict v-{kind}">{html.escape(text)}</div>')


def bars(items):
    """items : liste de (libellé, valeur)."""
    top = max([v for _, v in items] + [1])
    rows = "".join(
        f'<div class="bar-row"><div class="bar-l">{html.escape(str(l))}</div>'
        f'<div class="bar-t"><div class="bar-f" style="width:{100 * v / top:.1f}%"></div></div>'
        f'<div class="bar-v">{v}</div></div>' for l, v in items)
    st.html(f'<div class="bars">{rows}</div>')


def fmt_eur(value: float) -> str:
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def _level_class(level: str) -> str:
    return "b-n2" if level == cfg.LEVEL_N2 else "b-n1" if level == cfg.LEVEL_N1 else "b-low"


def _score_class(score, settings) -> str:
    return "b-n2" if score >= settings.n2 else "b-n1" if score >= settings.n1 else "b-low"


MONEY_COLS = {"MONTANT", "Volume", "Montant concerné"}
SCORE_COLS = {"RISK_SCORE", "Score client", "Score max"}
LEVEL_COLS = {"NIVEAU", "Niveau"}
WRAP_COLS = {"POURQUOI (typologies détectées)", "Signal d'alerte", "Colonnes manquantes", "Typologies", "LIBELLE"}


def show_table(df: pd.DataFrame, max_rows: int = 300, empty: str = "Aucune donnée à afficher."):
    """Tableau HTML clair (lisible dans tous les thèmes)."""
    if df is None or len(df) == 0:
        st.html(f'<div class="tbl-note">{html.escape(empty)}</div>')
        return
    shown = df.head(max_rows)
    settings = load_settings()
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in shown.columns)
    body = []
    for row in shown.itertuples(index=False):
        cells = []
        for col, value in zip(shown.columns, row):
            if pd.isna(value):
                cells.append("<td></td>")
            elif col in MONEY_COLS:
                cells.append(f'<td class="num">{fmt_eur(float(value))}</td>')
            elif col in SCORE_COLS:
                cells.append(f'<td><span class="badge {_score_class(value, settings)}">{int(value)}</span></td>')
            elif col in LEVEL_COLS:
                cells.append(f'<td><span class="badge {_level_class(value)}">{html.escape(str(value))}</span></td>')
            elif isinstance(value, pd.Timestamp):
                cells.append(f"<td>{value:%d/%m/%Y %H:%M}</td>")
            elif isinstance(value, float):
                cells.append(f'<td class="num">{value:,.2f}'.replace(",", " ").replace(".", ",") + "</td>")
            else:
                cls = ' class="wrap"' if col in WRAP_COLS else ""
                cells.append(f"<td{cls}>{html.escape(str(value))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.html(f'<div class="tbl-wrap"><table class="argus"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')
    if len(df) > max_rows:
        st.html(f'<div class="tbl-note">Affichage des {max_rows} premières lignes sur {len(df)} '
                f'— liste complète dans l\'export Excel.</div>')


def go_button(label: str, page: str, key: str, **kwargs):
    """Bouton qui ouvre une autre page."""
    if st.button(label, key=key, **kwargs):
        st.switch_page(page)


def footer():
    st.html(
        f'<div class="app-footer">Conçu et développé par <strong>{html.escape(cfg.AUTHOR)}</strong><br>'
        f'{cfg.APP_NAME} · version {cfg.VERSION} · © {datetime.now().year} — '
        f'Aide à la décision : ne remplace pas l\'analyse de l\'analyste N2</div>')


def card(title: str, body_html: str):
    """Carte de tableau de bord (HTML complet : texte, badges, tableaux)."""
    st.html(f'<div class="dcard"><div class="dcard-t">{html.escape(title)}</div>{body_html}</div>')


def wl_badges(items) -> str:
    return "".join(f'<span class="wl-badge">✔ {html.escape(str(i))}</span>' for i in items)


def sidebar_brand():
    st.sidebar.html(f'<div class="side-brand">🛡️ {html.escape(cfg.APP_NAME)}</div>'
                    f'<div class="side-sub">Compliance &amp; Fraud Analytics</div>')
