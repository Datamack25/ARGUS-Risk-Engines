"""Chargement, reconnaissance des colonnes (exacte, alias, floue) et normalisation des fichiers."""

import re
import warnings
from difflib import SequenceMatcher, get_close_matches

import numpy as np
import pandas as pd

from . import config as cfg
from .reference_lists import clean_token, strip_accents, to_iso2

# Champ canonique -> alias acceptés (en-têtes insensibles à la casse, aux accents et aux séparateurs)
CANONICAL = {
    "ID_TRANSACTION": ["TRANSACTION_ID", "ID", "N_OPERATION", "REFERENCE", "REF", "TX_ID"],
    "DATE": ["TX_DATE", "PERIODE", "DATE_OPERATION", "DATE_TRANSACTION", "TIMESTAMP", "TIMESTAMP_EVENT",
             "DATE_OP", "DT_OP", "DATE_VALEUR", "DT_TRX", "DATETIME", "HORODATAGE", "DATE_COMPTABLE"],
    "ID_CLIENT": ["CLIENT_ID", "USER_ID", "ID_JOUEUR", "ID_COMPTE", "NUMERO_CLIENT", "ID_ADHERENT",
                  "ID_ASSURE", "ID_SOUSCRIPTEUR"],
    "NOM_CLIENT": ["NOM", "NOM_DU_CLIENT", "NOM_ASSURE", "NOM_JOUEUR", "NOM_SOUSCRIPTEUR", "TITULAIRE_COMPTE_CLIENT"],
    "LIBELLE": ["TX_LABEL", "LIBELLE_OPERATION", "MOTIF", "DESCRIPTION", "COMMUNICATION", "OBJET",
                "DETAIL", "LABEL", "COMMENTAIRE", "INTITULE"],
    "MONTANT": ["TX_AMOUNT", "AMOUNT", "AMT", "MONTANT_EUR", "SOMME", "VALEUR", "TOTAL",
                "MONTANT_TRANSACTION", "MONTANT_OPERATION", "MONTANT_TTC"],
    "DEVISE": ["TX_CURRENCY", "MONNAIE", "CURR", "CURRENCY", "ISO_DEVISE", "CODE_DEVISE"],
    "SENS": ["DIRECTION", "SENS_OPERATION", "DEBIT_CREDIT", "CREDIT_DEBIT", "D_C"],
    "TYPE_OPERATION": ["TYPOLOGIE_FLUX", "TYPE_FLUX", "TYPE", "TYPE_OP", "NATURE", "TYPE_TRANSACTION"],
    "MOYEN_PAIEMENT": ["PAYMENT_METHOD", "MOYEN", "MODE_PAIEMENT", "SUPPORT"],
    "PAYS": ["COUNTRY", "PAYS_DESTINATION", "CODE_PAYS", "PAYS_BENEFICIAIRE", "PAYS_CONTREPARTIE",
             "PAYS_ORIGINE", "ISO_PAYS"],
    "PAYS_RESIDENCE": ["RESIDENCE", "PAYS_RESIDENCE_FISCALE", "RESIDENCE_FISCALE", "PAYS_DE_RESIDENCE"],
    "PPE_SANCTION": ["PPE", "PEP", "SANCTION", "MATCH_SANCTION", "PEP_SANCTION"],
    "NOM_TITULAIRE_COMPTE": ["TITULAIRE_IBAN", "NOM_TITULAIRE_IBAN", "HOLDER_NAME", "TITULAIRE_RIB",
                             "NOM_TITULAIRE", "TITULAIRE"],
    "CONTREPARTIE": ["DESTINATAIRE", "BENEFICIAIRE", "TIERS", "EMETTEUR", "DONNEUR_D_ORDRE",
                     "DONNEUR_ORDRE", "COUNTERPARTY"],
    "IBAN_CONTREPARTIE": ["IBAN", "IBAN_DESTINATAIRE", "COMPTE", "NUMERO_COMPTE", "RIB", "ACCOUNT",
                          "DESTINATION_IBAN", "IBAN_DESTINATION"],
    "IP": ["IP_ADDRESS", "ADRESSE_IP"],
    "BIN_CARTE": ["BIN", "CARD_BIN", "BIN_CB"],
    "STATUT_KYC": ["KYC", "KYC_STATUS", "ETAT_KYC"],
    "STATUT": ["STATUT_OPERATION", "STATUS", "ETAT"],
    "CANAL": ["CHANNEL", "CANAL_DISTRIBUTION"],
    "INTERDIT_ANJ": ["INTERDIT_JEU", "FICHIER_INTERDITS", "INTERDIT_DE_JEU", "ANJ_INTERDIT"],
}

FIELD_LABELS = {
    "MONTANT": "Montant (obligatoire)", "DATE": "Date", "DEVISE": "Devise", "LIBELLE": "Libellé",
    "CONTREPARTIE": "Contrepartie", "IBAN_CONTREPARTIE": "IBAN / compte", "PAYS": "Pays",
    "SENS": "Sens (débit / crédit)", "TYPE_OPERATION": "Type d'opération", "ID_CLIENT": "Identifiant client",
    "NOM_CLIENT": "Nom du client", "ID_TRANSACTION": "Identifiant de l'opération",
    "MOYEN_PAIEMENT": "Moyen de paiement", "PAYS_RESIDENCE": "Pays de résidence",
    "PPE_SANCTION": "PPE / sanctions", "NOM_TITULAIRE_COMPTE": "Titulaire du compte de contrepartie",
    "IP": "Adresse IP", "BIN_CARTE": "BIN de carte", "STATUT_KYC": "Statut KYC", "STATUT": "Statut de l'opération",
    "CANAL": "Canal", "INTERDIT_ANJ": "Interdit de jeu (ANJ)",
}
REQUIRED_FIELDS = ["MONTANT"]
FUZZY_CUTOFF = 0.85

_NA_VALUES = ["", "NaN", "nan", "NULL", "null", "None", "N/A"]   # "NA" volontairement conservé (Namibie)

IN_KEYWORDS = ("DEPOT", "CREDIT", "ENCAISS", "ENTRANT", "VERSEMENT", "COTISATION", "PRIME",
               "GAIN", "RECHARGE", "RECU")
OUT_KEYWORDS = ("RETRAIT", "DEBIT", "SORTANT", "PAIEMENT", "EMIS", "REMBOURS", "RACHAT",
                "DECAISS", "SINISTRE", "INDEMN")


def _norm_header(header) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", strip_accents(str(header)).upper()).strip("_")


ALIAS_LOOKUP = {}
for _canon, _aliases in CANONICAL.items():
    for _alias in _aliases:
        ALIAS_LOOKUP.setdefault(_norm_header(_alias), _canon)


# ---------------------------------------------------------------------------
# Chargement
# ---------------------------------------------------------------------------
def load_file(uploaded) -> pd.DataFrame:
    """Lit un fichier CSV ou Excel (objet UploadedFile Streamlit, BytesIO nommé ou chemin)."""
    name = getattr(uploaded, "name", str(uploaded)).lower()
    kwargs = dict(keep_default_na=False, na_values=_NA_VALUES)
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(uploaded, **kwargs)
    else:
        df, last_error = None, None
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                if hasattr(uploaded, "seek"):
                    uploaded.seek(0)
                df = pd.read_csv(uploaded, sep=None, engine="python", encoding=encoding, **kwargs)
                break
            except UnicodeDecodeError as exc:
                last_error = exc
        if df is None:
            raise ValueError(f"Encodage du fichier non reconnu : {last_error}")
    df.columns = [str(c) for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Reconnaissance des colonnes : exacte -> alias -> floue (>= 85 %) ; profil enregistré prioritaire
# ---------------------------------------------------------------------------
def _fuzzy_best(key: str, names: list):
    """Meilleure correspondance floue (thefuzz si installé, sinon difflib) ; (nom, ratio 0-1) ou None."""
    try:
        from thefuzz import fuzz, process
        found = process.extractOne(key, names, scorer=fuzz.ratio)
        if found and found[1] >= FUZZY_CUTOFF * 100:
            return found[0], found[1] / 100
    except ImportError:
        close = get_close_matches(key, names, n=1, cutoff=FUZZY_CUTOFF)
        if close:
            return close[0], SequenceMatcher(None, key, close[0]).ratio()
    return None


def detect_mapping(columns, saved: dict = None, synonyms: dict = None) -> dict:
    """Retourne {"mapping": {champ: en-tête}, "details": [...], "unmapped": [...], "missing_required": [...]}."""
    columns = [str(c) for c in columns]
    mapping, details = {}, []

    def assign(canon, header, method, score=1.0):
        if canon in mapping or header in mapping.values():
            return False
        mapping[canon] = header
        details.append({"header": header, "field": canon, "method": method, "score": round(score, 2)})
        return True

    for canon, header in (saved or {}).items():
        if canon in CANONICAL and header in columns:
            assign(canon, header, "profil enregistré")
    keys = {c: _norm_header(c) for c in columns}
    lookup = dict(ALIAS_LOOKUP)                           # synonymes ajoutés par l'administrateur
    for canon, words in (synonyms or {}).items():
        if canon in CANONICAL:
            for word in words:
                lookup[_norm_header(word)] = canon
    for col in columns:                                   # 1) nom canonique exact
        if keys[col] in CANONICAL:
            assign(keys[col], col, "exacte")
    for col in columns:                                   # 2) alias connu
        canon = lookup.get(keys[col])
        if canon:
            assign(canon, col, "alias")
    names = list(lookup) + list(CANONICAL)                # 3) correspondance floue (>= 85 %)
    for col in columns:
        if col in mapping.values() or len(keys[col]) < 4:
            continue
        best = _fuzzy_best(keys[col], names)
        if best:
            canon = lookup.get(best[0], best[0] if best[0] in CANONICAL else None)
            if canon:
                assign(canon, col, "approximative", best[1])
    return {
        "mapping": mapping, "details": details,
        "unmapped": [c for c in columns if c not in mapping.values()],
        "missing_required": [f for f in REQUIRED_FIELDS if f not in mapping],
    }


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def _to_number(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    s = series.astype(str).str.replace("[€\\s\u202f\xa0]", "", regex=True)
    both = s.str.contains(",", regex=False) & s.str.contains(".", regex=False)
    s = s.where(~both, s.str.replace(".", "", regex=False))
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _parse_dates(series: pd.Series) -> pd.Series:
    """Dates ISO (AAAA-MM-JJ) d'abord, puis formats français (JJ/MM/AAAA) pour le reste."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(series, errors="coerce", format="ISO8601")
        rest = parsed.isna() & series.notna() & (series.astype(str).str.strip() != "")
        if rest.any():
            parsed = parsed.copy()
            parsed[rest] = pd.to_datetime(series[rest], errors="coerce", dayfirst=True)
    return parsed


def _classify_direction(value: str) -> str:
    token = clean_token(value)
    if not token:
        return "INCONNU"
    if token in ("C", "CR"):
        return "ENTRANT"
    if token in ("D", "DB"):
        return "SORTANT"
    if any(k in token for k in IN_KEYWORDS):
        return "ENTRANT"
    if any(k in token for k in OUT_KEYWORDS):
        return "SORTANT"
    return "INCONNU"


def _map_direction(series: pd.Series) -> pd.Series:
    mapping = {v: _classify_direction(v) for v in series.dropna().unique()}
    return series.map(mapping).fillna("INCONNU")


def normalize(raw: pd.DataFrame, exclusions=None, mapping: dict = None, fx_rates: dict = None,
              synonyms: dict = None):
    """Retourne (DataFrame normalisé, informations).

    exclusions : mots de libellé à ignorer (par défaut : config.EXCLUSIONS)
    mapping    : {champ canonique: en-tête du fichier} ; détecté automatiquement si absent
    fx_rates   : taux de conversion vers l'euro {"USD": 0.92} (voir Administration › Listes de référence)
    """
    df = raw.copy()
    df.columns = [str(c) for c in df.columns]
    notes = []
    rows_file = len(df)
    blank = df.apply(lambda col: col.isna() | (col.astype(str).str.strip() == ""), axis=0).all(axis=1)
    rows_empty = int(blank.sum())
    if rows_empty:
        df = df[~blank].copy()
        notes.append(f"{rows_empty} ligne(s) vide(s) ou parasite(s) ignorée(s).")

    # 1) Correspondance des colonnes
    if mapping is None:
        detection = detect_mapping(df.columns, synonyms=synonyms)
        mapping, details = detection["mapping"], detection["details"]
    else:
        mapping = {k: v for k, v in mapping.items() if v in df.columns}
        details = [{"header": h, "field": c, "method": "validée", "score": 1.0} for c, h in mapping.items()]
    rename = {header: canon for canon, header in mapping.items()}
    for col in df.columns:
        rename.setdefault(col, _norm_header(col))
    df = df.rename(columns=rename)
    df = df.loc[:, ~df.columns.duplicated()]
    unrecognized = sorted(c for c in df.columns if c not in CANONICAL)

    if "MONTANT" not in df.columns:
        raise ValueError("Colonne MONTANT introuvable. Colonnes détectées : "
                         + ", ".join(map(str, raw.columns)))
    rows_raw = len(df)

    # 2) Montants et devises
    df["MONTANT"] = _to_number(df["MONTANT"])
    invalid = int(df["MONTANT"].isna().sum())
    if invalid:
        notes.append(f"{invalid} ligne(s) ignorée(s) : montant illisible ou vide.")
        df = df[df["MONTANT"].notna()].copy()
    if df.empty:
        raise ValueError("Aucune ligne exploitable : tous les montants sont vides ou illisibles.")
    if "DEVISE" in df.columns:
        currency = df["DEVISE"].fillna("").astype(str).str.strip().str.upper()
        rates = {str(k).upper(): float(v) for k, v in (fx_rates or {}).items()}
        foreign = currency[~currency.isin(["", "EUR", "€"])]
        known = foreign[foreign.isin(rates)]
        if len(known):
            df.loc[known.index, "MONTANT"] = df.loc[known.index, "MONTANT"] * known.map(rates)
            notes.append(f"{len(known)} opération(s) convertie(s) en EUR avec les taux de la page Administration.")
        unknown = sorted(set(foreign[~foreign.isin(rates)]))
        if unknown:
            notes.append("Devise(s) sans taux de conversion (montants traités tels quels) : " + ", ".join(unknown)
                         + ". Renseignez les taux dans Administration › Devises.")

    # 3) Dates
    if "DATE" in df.columns:
        df["DATE"] = _parse_dates(df["DATE"])
        if df["DATE"].isna().all():
            df = df.drop(columns="DATE")
            notes.append("Colonne DATE illisible : analyses temporelles désactivées.")
        elif df["DATE"].isna().any():
            notes.append(f"{int(df['DATE'].isna().sum())} date(s) illisible(s).")

    # 4) Sens (ENTRANT / SORTANT)
    sens = pd.Series("INCONNU", index=df.index, dtype=object)
    if "SENS" in df.columns:
        sens = _map_direction(df["SENS"])
    if "TYPE_OPERATION" in df.columns:
        sens = sens.where(sens != "INCONNU", _map_direction(df["TYPE_OPERATION"]))
    if (df["MONTANT"] < 0).any():
        by_sign = np.where(df["MONTANT"] < 0, "SORTANT", "ENTRANT")
        sens = sens.where(sens != "INCONNU", pd.Series(by_sign, index=df.index))
    if (sens != "INCONNU").any():
        df["SENS"] = sens
    else:
        df = df.drop(columns="SENS", errors="ignore")
        notes.append("Sens des opérations indéterminé : ajoutez SENS ou TYPE_OPERATION.")
    df["MONTANT"] = df["MONTANT"].abs()

    # 5) IBAN, pays et contrepartie
    if "IBAN_CONTREPARTIE" not in df.columns and "CONTREPARTIE" in df.columns:
        compact = df["CONTREPARTIE"].fillna("").astype(str).str.replace(r"\s", "", regex=True).str.upper()
        looks_iban = compact.str.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
        if looks_iban.any():
            df["IBAN_CONTREPARTIE"] = compact.where(looks_iban, "")
    if "IBAN_CONTREPARTIE" in df.columns:
        iban = df["IBAN_CONTREPARTIE"].fillna("").astype(str).str.replace(r"\s", "", regex=True).str.upper()
        iban_country = iban.str.extract(r"^([A-Z]{2})\d{2}")[0].fillna("")
        if "PAYS" not in df.columns:
            df["PAYS"] = iban_country.replace("", np.nan)
        if "CONTREPARTIE" not in df.columns:
            df["CONTREPARTIE"] = df["IBAN_CONTREPARTIE"]
    else:
        iban_country = pd.Series("", index=df.index)
    ref = iban_country.copy()
    if "PAYS" in df.columns:
        by_country = df["PAYS"].map(to_iso2)
        ref = ref.where(ref != "", by_country)
    df["PAYS_REF"] = ref.replace("", np.nan)

    # 6) Identifiant client
    client_known = True
    if "ID_CLIENT" not in df.columns:
        if "NOM_CLIENT" in df.columns:
            df["ID_CLIENT"] = df["NOM_CLIENT"]
        else:
            client_known = False
            notes.append("Aucun identifiant client : le fichier est traité comme un seul compte.")
    if "ID_CLIENT" in df.columns:
        df["ID_CLIENT"] = df["ID_CLIENT"].astype(str).str.strip().replace({"": "INCONNU"})

    # 7) Exclusion des opérations techniques (frais, rejets, taxes…)
    excluded = 0
    exclusions = cfg.EXCLUSIONS if exclusions is None else exclusions
    if "LIBELLE" in df.columns and exclusions:
        label = (df["LIBELLE"].fillna("").astype(str).str.normalize("NFKD")
                 .str.encode("ascii", "ignore").str.decode("ascii").str.upper()
                 .str.replace(r"[^A-Z0-9]", "", regex=True))
        pattern = "|".join(re.sub(r"[^A-Z0-9]", "", strip_accents(e).upper()) for e in exclusions)
        mask = label.str.contains(pattern, regex=True)
        excluded = int(mask.sum())
        df = df[~mask].copy()
    if df.empty:
        raise ValueError("Toutes les opérations ont été exclues (frais, rejets, taxes…).")

    df = df.reset_index(drop=True)
    info = {
        "rows_file": rows_file, "rows_empty": rows_empty, "rows_raw": rows_raw, "rows_invalid": invalid, "rows_excluded": excluded,
        "rows_analyzed": len(df), "recognized": sorted(mapping), "unrecognized": unrecognized,
        "mapping": mapping, "mapping_details": details, "client_known": client_known, "notes": notes,
    }
    return df, info
