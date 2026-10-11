"""Contexte KYC / transaction, référentiel sectoriel et auto-enrichissement (fichiers CSV).

Fichiers (racine du projet, ou ARGUS_CONFIG_DIR) :
  sectors_reference.csv        Sector_Code, Sector_Name, Risk_Level   (géré par l'Administration)
  client_profiles_history.csv  une ligne par client et par analyse validée (moyennes, volumes, score)
  fraud_patterns_learned.csv   une ligne par typologie déclenchée à chaque analyse validée
"""

from datetime import datetime

import pandas as pd

from . import settings as cs
from .reference_lists import to_iso2

SECTORS_FILE = "sectors_reference.csv"
PROFILES_FILE = "client_profiles_history.csv"
PATTERNS_FILE = "fraud_patterns_learned.csv"

SECTOR_COLS = ["Sector_Code", "Sector_Name", "Risk_Level"]
PROFILE_COLS = ["analysis_date", "source", "client_id", "tx_count", "total_volume", "avg_amount",
                "max_amount", "client_score", "client_level", "typologies"]
PATTERN_COLS = ["analysis_date", "source", "typology_code", "typology_name", "alerts", "amount_concerned",
                "clients_concerned"]

RISK_LEVELS = ["Faible", "Moyen", "Élevé", "Critique"]
DEFAULT_SECTORS = [
    ("BANQ", "Banque / services financiers", "Moyen"), ("ASSU", "Assurance", "Moyen"),
    ("JEUX", "Jeux d'argent en ligne", "Élevé"), ("PAIE", "Établissement de paiement / FinTech", "Moyen"),
    ("CRYP", "Crypto-actifs / PSAN", "Critique"), ("IMMO", "Immobilier", "Élevé"),
    ("BTP", "BTP / construction", "Élevé"), ("RESTO", "Restauration / HCR", "Moyen"),
    ("NEGOCE", "Négoce de métaux et pierres précieuses", "Critique"), ("ART", "Art et antiquités", "Élevé"),
    ("TRANSP", "Transport / logistique", "Moyen"), ("COMM", "Commerce de détail", "Faible"),
    ("SANTE", "Santé", "Faible"), ("ASSO", "Associations / fondations", "Moyen"),
    ("CONSEIL", "Conseil / services aux entreprises", "Moyen"), ("PUBLIC", "Administration publique", "Faible"),
]


def _path(name: str):
    return cs.config_dir() / name


def ensure_files():
    """Crée les fichiers CSV s'ils n'existent pas."""
    try:
        if not _path(SECTORS_FILE).exists():
            pd.DataFrame(DEFAULT_SECTORS, columns=SECTOR_COLS).to_csv(_path(SECTORS_FILE), index=False, encoding="utf-8")
        if not _path(HISTORY_FILE).exists():
            pd.DataFrame(columns=HISTORY_COLS).to_csv(_path(HISTORY_FILE), index=False, encoding="utf-8")
        for name, cols in ((PROFILES_FILE, PROFILE_COLS), (PATTERNS_FILE, PATTERN_COLS)):
            if not _path(name).exists():
                pd.DataFrame(columns=cols).to_csv(_path(name), index=False, encoding="utf-8")
    except OSError:
        pass


def load_csv(name: str, cols: list) -> pd.DataFrame:
    ensure_files()
    try:
        df = pd.read_csv(_path(name), dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=cols)
    for col in cols:
        if col not in df.columns:
            df[col] = ""
    return df[cols]


def load_sectors() -> pd.DataFrame:
    df = load_csv(SECTORS_FILE, SECTOR_COLS)
    return df if len(df) else pd.DataFrame(DEFAULT_SECTORS, columns=SECTOR_COLS)


def save_csv(name: str, df: pd.DataFrame):
    df.to_csv(_path(name), index=False, encoding="utf-8")


def sector_risk(code_or_name: str) -> str:
    if not code_or_name:
        return ""
    df = load_sectors()
    hit = df[(df["Sector_Code"] == code_or_name) | (df["Sector_Name"] == code_or_name)]
    return str(hit.iloc[0]["Risk_Level"]) if len(hit) else ""


# ---------------------------------------------------------------------------
def apply_context(res, context: dict, settings) -> list:
    """Majore le score des opérations déjà alertées selon le contexte KYC / transaction.

    Retourne la liste des constats de contexte (texte). Modifie `res.df` et `res.clients`.
    """
    from .engine import _client_profiles
    if not context:
        return []
    cfg_ctx = settings.context_cfg or {}
    b_high, b_crit = int(cfg_ctx.get("bonus_high", 10)), int(cfg_ctx.get("bonus_critical", 20))
    factor = float(cfg_ctx.get("kyc_volume_factor", 2.0))
    tx, kyc = context.get("transaction", {}), context.get("kyc", {})
    df = res.df
    notes, bonus = [], pd.Series(0, index=df.index, dtype=float)
    alerted = df["NB_TYPOLOGIES"] > 0

    level = sector_risk(tx.get("secteur_contrepartie", ""))
    if level in ("Élevé", "Critique"):
        points = b_crit if level == "Critique" else b_high
        bonus[alerted] += points
        notes.append(f"Secteur de la contrepartie « {tx.get('secteur_contrepartie')} » classé {level} (+{points} pts).")
    for key, label in (("pays_origine", "d'origine"), ("pays_destination", "de destination")):
        iso = to_iso2(tx.get(key, ""))
        if iso and iso in settings.high_risk:
            bonus[alerted] += b_high
            notes.append(f"Pays {label} ({tx.get(key)}) à risque élevé (+{b_high} pts).")
        elif iso and iso in settings.tax_havens:
            bonus[alerted] += b_high // 2
            notes.append(f"Pays {label} ({tx.get(key)}) juridiction fiscale sensible (+{b_high // 2} pts).")
    if tx.get("type_contrepartie") in ("Personne physique non résidente", "Société offshore / écran"):
        bonus[alerted] += b_high
        notes.append(f"Type de contrepartie « {tx['type_contrepartie']} » sensible (+{b_high} pts).")
    if tx.get("effet_generateur"):
        bonus[alerted] += b_high // 2
        notes.append(f"Effet générateur déclaré : « {tx['effet_generateur']} » (+{b_high // 2} pts).")

    declared = float(kyc.get("volume_annuel_declare") or 0)
    if declared > 0 and "ID_CLIENT" in df.columns:
        total = df["MONTANT"].sum()
        if total > declared * factor:
            bonus[alerted] += b_high
            notes.append(f"Volume analysé {total:,.0f} € supérieur à {factor:g} × le volume annuel déclaré au KYC "
                         f"({declared:,.0f} €) (+{b_high} pts).".replace(",", " "))
    if kyc.get("ppe"):
        bonus[alerted] += b_high
        notes.append(f"Client déclaré PPE (+{b_high} pts).")

    if bonus.any():
        df["RISK_SCORE"] = (df["RISK_SCORE"] + bonus).clip(upper=settings.cap).astype(int)
        df["NIVEAU"] = df["RISK_SCORE"].map(settings.level_for)
        res.clients = _client_profiles(df, res.flags, settings)
    return notes


def learn(res, source: str, settings) -> int:
    """Ajoute l'analyse validée aux deux fichiers d'apprentissage. Retourne le nombre de lignes écrites."""
    if not settings.learning_enabled:
        return 0
    ensure_files()
    now = datetime.now().isoformat(timespec="seconds")
    df, rows = res.df, 0
    try:
        if "ID_CLIENT" in df.columns:
            g = df.groupby("ID_CLIENT")
            prof = pd.DataFrame({
                "tx_count": g.size(), "total_volume": g["MONTANT"].sum().round(2),
                "avg_amount": g["MONTANT"].mean().round(2), "max_amount": g["MONTANT"].max().round(2),
                "client_score": g["RISK_SCORE"].max(),
            }).reset_index().rename(columns={"ID_CLIENT": "client_id"})
            prof["client_level"] = prof["client_score"].map(settings.level_for)
            prof["typologies"] = prof["client_id"].map(
                df[df["NB_TYPOLOGIES"] > 0].groupby("ID_CLIENT")["ALERTES"].agg(lambda s: " | ".join(sorted(set(s)))[:300]
                                                                              )).fillna("")
            prof.insert(0, "source", source)
            prof.insert(0, "analysis_date", now)
            old = load_csv(PROFILES_FILE, PROFILE_COLS)
            save_csv(PROFILES_FILE, pd.concat([old, prof[PROFILE_COLS].astype(str)], ignore_index=True))
            rows += len(prof)
        pats = []
        for code, flag in res.flags.items():
            if flag.any():
                sub = df[flag]
                pats.append({"analysis_date": now, "source": source, "typology_code": code,
                             "typology_name": res.codes_to_names[code], "alerts": int(flag.sum()),
                             "amount_concerned": round(float(sub["MONTANT"].sum()), 2),
                             "clients_concerned": int(sub["ID_CLIENT"].nunique()) if "ID_CLIENT" in sub.columns else 0})
        if pats:
            old = load_csv(PATTERNS_FILE, PATTERN_COLS)
            save_csv(PATTERNS_FILE, pd.concat([old, pd.DataFrame(pats).astype(str)], ignore_index=True))
            rows += len(pats)
    except OSError:
        return 0
    return rows


# ---------------------------------------------------------------------------
# Journal des analyses (alimente l'accueil / tableau de bord exécutif)
# ---------------------------------------------------------------------------
HISTORY_FILE = "analyses_history.csv"
HISTORY_COLS = ["analysis_date", "source", "files", "rows", "volume", "suspects", "n1", "n2", "exempt",
                "clients_flagged"]


def load_history() -> pd.DataFrame:
    try:
        df = pd.read_csv(_path(HISTORY_FILE), dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=HISTORY_COLS)
    for col in HISTORY_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[HISTORY_COLS]


def log_analysis(res, source: str, n_files: int, settings) -> bool:
    """Ajoute une ligne au journal des analyses (une par analyse effectuée)."""
    from . import config as cfg
    df = res.df
    exempt = int((df["QUALIFICATION"].fillna("") != "").sum()) if "QUALIFICATION" in df.columns else 0
    row = {
        "analysis_date": datetime.now().isoformat(timespec="seconds"), "source": source, "files": n_files,
        "rows": len(df), "volume": round(float(df["MONTANT"].sum()), 2),
        "suspects": int((df["NB_TYPOLOGIES"] > 0).sum()),
        "n1": int((df["NIVEAU"] == cfg.LEVEL_N1).sum()), "n2": int((df["NIVEAU"] == cfg.LEVEL_N2).sum()),
        "exempt": exempt,
        "clients_flagged": int(df.loc[df["NB_TYPOLOGIES"] > 0, "ID_CLIENT"].nunique()) if "ID_CLIENT" in df.columns else 0,
    }
    try:
        old = load_history()
        save_csv(HISTORY_FILE, pd.concat([old, pd.DataFrame([row]).astype(str)], ignore_index=True)[HISTORY_COLS])
        return True
    except OSError:
        return False


def save_exports(docx_bytes: bytes, xlsx_bytes: bytes) -> list:
    """Copie les livrables dans le dossier exports/ (meilleur effort ; le téléchargement reste la voie principale)."""
    folder = cs.config_dir() / "exports"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = []
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in ((f"argus_note_N2_{stamp}.docx", docx_bytes), (f"argus_analyse_{stamp}.xlsx", xlsx_bytes)):
            (folder / name).write_bytes(data)
            saved.append(f"exports/{name}")
    except OSError:
        pass
    return saved
