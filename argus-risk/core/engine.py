"""Moteur de détection et de scoring.

Principe : chacune des typologies du catalogue est évaluée par un
détecteur vectorisé. Une typologie dont les colonnes requises sont absentes est
marquée « Non évaluable » (jamais « aucune alerte ») afin de ne pas donner une
fausse impression de couverture. Le score d'une opération est la somme des poids
des typologies déclenchées, plafonnée à SCORE_CAP.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

import re

import numpy as np
import pandas as pd

from . import config as cfg
from .reference_lists import NAME_STOPWORDS, TRUTHY, clean_token, strip_accents, to_iso2
from .settings import Settings, load_settings
from .typologies import COLUMN_LABELS, required_columns

INF = float("inf")


# ---------------------------------------------------------------------------
# Contexte d'analyse (tableaux numpy précalculés)
# ---------------------------------------------------------------------------
def _clean_series(s: pd.Series) -> pd.Series:
    return (s.fillna("").astype(str).str.normalize("NFKD").str.encode("ascii", "ignore")
            .str.decode("ascii").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True))


class Ctx:
    def __init__(self, df: pd.DataFrame, settings: Settings):
        self.settings = settings
        d = df.reset_index(drop=True)
        self.df, self.n = d, len(d)
        self.amount = d["MONTANT"].abs().fillna(0.0).to_numpy(dtype=float)

        if "SENS" in d.columns:
            self.sens = d["SENS"].fillna("INCONNU").to_numpy(dtype=object)
        else:
            self.sens = np.full(self.n, "INCONNU", dtype=object)
        self.is_in = self.sens == "ENTRANT"
        self.is_out = self.sens == "SORTANT"

        self.client_known = "ID_CLIENT" in d.columns and d["ID_CLIENT"].notna().any()
        self.client = (d["ID_CLIENT"].astype(str) if self.client_known
                       else pd.Series("CLIENT_UNIQUE", index=d.index))

        self.has_date = "DATE" in d.columns and d["DATE"].notna().any()
        if self.has_date:
            dt = d["DATE"]
            self.hours = ((dt - dt.min()).dt.total_seconds() / 3600.0).fillna(0.0).to_numpy(float)
            self.has_tod = bool(((dt.dt.hour.fillna(0) + dt.dt.minute.fillna(0)) > 0).any())
        else:
            self.hours = np.zeros(self.n)
            self.has_tod = False

        parts = [d[c].fillna("").astype(str) for c in ("LIBELLE", "STATUT", "TYPE_OPERATION")
                 if c in d.columns]
        if parts:
            text = parts[0]
            for p in parts[1:]:
                text = text + " " + p
            self.blob = _clean_series(text)
            if not (self.blob != "").any():
                self.blob = None
        else:
            self.blob = None

        self._cache = {}
        self.last_n = None          # fenêtre « N dernières transactions du client » (None = désactivée)
        self.extra = {}
        positions = pd.Series(np.arange(self.n)).groupby(self.client.to_numpy())
        self.groups = []
        for idx in positions.indices.values():
            idx = np.asarray(idx)
            self.groups.append(idx[np.argsort(self.hours[idx], kind="stable")])

    # -- disponibilité des colonnes logiques --
    def has(self, col: str) -> bool:
        if col == "CLIENT":
            return self.client_known
        if col == "HEURE":
            return self.has_tod
        if col == "TEXTE":
            return self.blob is not None
        if col == "DATE":
            return self.has_date
        if col == "SENS":
            return bool((self.is_in | self.is_out).any())
        if col == "PAYS_REF":
            return "PAYS_REF" in self.df.columns and bool(self.df["PAYS_REF"].notna().any())
        return col in self.df.columns and bool(self.df[col].notna().any()) and \
            bool((self.df[col].astype(str).str.strip() != "").any())

    # -- utilitaires --
    def cleaned(self, col: str) -> pd.Series:
        if col not in self._cache:
            self._cache[col] = _clean_series(self.df[col])
        return self._cache[col]

    def in_set(self, col: str, values) -> np.ndarray:
        wanted = {clean_token(v) for v in values}
        return self.cleaned(col).isin(wanted).to_numpy()

    def keyword_mask(self, keywords) -> np.ndarray:
        pattern = "|".join(clean_token(k) for k in keywords)
        return self.blob.str.contains(pattern, regex=True).to_numpy()

    def rolling(self, weight: np.ndarray, window_h: float, last_n: int = None):
        """Somme et nombre (poids > 0) sur la fenêtre glissante [t - window_h ; t], par client.

        Si `last_n` est renseigné, la fenêtre est en plus limitée aux `last_n` dernières
        transactions du client (fenêtre courte : détecte les signaux faibles).
        """
        total, count = np.zeros(self.n), np.zeros(self.n)
        flag = (weight > 0).astype(float)
        for idx in self.groups:
            h, w, k = self.hours[idx], weight[idx], flag[idx]
            cs, ck = np.cumsum(w), np.cumsum(k)
            left = np.searchsorted(h, h - window_h, side="left")
            right = np.searchsorted(h, h, side="right") - 1
            if last_n:
                left = np.maximum(left, right - (int(last_n) - 1))
            prev = np.maximum(left - 1, 0)
            total[idx] = cs[right] - np.where(left > 0, cs[prev], 0.0)
            count[idx] = ck[right] - np.where(left > 0, ck[prev], 0.0)
        return total, count


def _rolling_distinct(ctx: Ctx, mask: np.ndarray, codes: np.ndarray, window_h: float) -> np.ndarray:
    """Nombre de valeurs distinctes (codes) parmi les lignes masquées, fenêtre glissante par client."""
    out = np.zeros(ctx.n)
    for idx in ctx.groups:
        h, m, c = ctx.hours[idx], mask[idx], codes[idx]
        counts, left, distinct = {}, 0, 0
        for j in range(len(idx)):
            if m[j]:
                counts[c[j]] = counts.get(c[j], 0) + 1
                if counts[c[j]] == 1:
                    distinct += 1
            while h[j] - h[left] > window_h:
                if m[left]:
                    counts[c[left]] -= 1
                    if counts[c[left]] == 0:
                        distinct -= 1
                left += 1
            out[idx[j]] = distinct
    return out


def _count_by_key(ctx: Ctx, keys: np.ndarray, mask: np.ndarray, window_h: float) -> np.ndarray:
    """Nombre de lignes masquées de même clé dans la fenêtre glissante."""
    out = np.zeros(ctx.n)
    idxs = np.flatnonzero(mask)
    if len(idxs) == 0:
        return out
    for pos in pd.Series(np.arange(len(idxs))).groupby(np.asarray(keys)[idxs]).indices.values():
        rows = idxs[pos]
        rows = rows[np.argsort(ctx.hours[rows], kind="stable")]
        h = ctx.hours[rows]
        left = np.searchsorted(h, h - window_h, side="left")
        right = np.searchsorted(h, h, side="right")
        out[rows] = right - left
    return out


def _roll(ctx: Ctx, p: dict, weight: np.ndarray, default_window: float = INF):
    """Fenêtre glissante avec limitation aux N dernières transactions (détecteurs comportementaux)."""
    n = ctx.last_n
    if n:
        n = max(int(n), int(p.get("min_count", 0)))
    return ctx.rolling(weight, p.get("window_h", default_window), last_n=n or None)


def _base(ctx: Ctx, p: dict) -> np.ndarray:
    """Masque des opérations concernées (sens, moyen de paiement, canal)."""
    mask = np.ones(ctx.n, dtype=bool)
    if p.get("direction") == "in":
        mask &= ctx.is_in
    elif p.get("direction") == "out":
        mask &= ctx.is_out
    if "methods" in p:
        mask &= ctx.in_set("MOYEN_PAIEMENT", p["methods"])
    if "channels" in p:
        mask &= ctx.in_set("CANAL", p["channels"])
    return mask


# ---------------------------------------------------------------------------
# Détecteurs : (ctx, params) -> tableau booléen par opération
# ---------------------------------------------------------------------------
def d_pass_through(ctx, p):
    inflow = ctx.is_in & (ctx.keyword_mask(p["credit_keywords"]) if "credit_keywords" in p else True)
    credits = np.where(inflow, ctx.amount, 0.0)
    total, _ = _roll(ctx, p, credits, 48)
    return ctx.is_out & (total >= p.get("min_amount", 1000)) & \
        (ctx.amount >= p.get("ratio", 0.85) * total) & (total > 0)


def d_structuring(ctx, p):
    thr = p["threshold"]
    band = _base(ctx, p) & (ctx.amount >= thr * p.get("band_low", 0.8)) & (ctx.amount < thr)
    _, count = _roll(ctx, p, band.astype(float))
    return band & (count >= p.get("min_count", 3))


def d_cash_cumul(ctx, p):
    cash = _base(ctx, p)
    total, _ = ctx.rolling(np.where(cash, ctx.amount, 0.0), p.get("window_h", INF))
    return cash & (total >= p["threshold"])


def d_velocity(ctx, p):
    base = _base(ctx, p)
    _, count = _roll(ctx, p, base.astype(float), DAY_H)
    return base & (count >= p["min_count"])


DAY_H = 24


def d_high_risk_country(ctx, p):
    iso = ctx.df["PAYS"].map(to_iso2)
    mask = iso.isin(list(ctx.settings.high_risk)).to_numpy() & _base(ctx, p)
    if "max_amount" in p:
        mask &= ctx.amount <= p["max_amount"]
    if "min_count" in p:
        _, count = ctx.rolling(mask.astype(float), p.get("window_h", INF))
        mask &= count >= p["min_count"]
    return mask


def d_tax_haven(ctx, p):
    return ctx.df["PAYS"].map(to_iso2).isin(list(ctx.settings.tax_havens)).to_numpy()


def d_non_sepa(ctx, p):
    iso = ctx.df["PAYS"].map(to_iso2)
    return ((iso != "") & ~iso.isin(list(ctx.settings.sepa))).to_numpy()


def _name_key(value) -> str:
    text = strip_accents(str(value)).upper()
    tokens = [t for t in "".join(c if c.isalpha() else " " for c in text).split()
              if t not in NAME_STOPWORDS]
    return " ".join(sorted(tokens))


def d_third_party(ctx, p):
    a = ctx.df["NOM_CLIENT"].fillna("").map(_name_key).to_numpy()
    b = ctx.df["NOM_TITULAIRE_COMPTE"].fillna("").map(_name_key).to_numpy()
    cache, flag = {}, np.zeros(ctx.n, dtype=bool)
    for i in range(ctx.n):
        if not a[i] or not b[i]:
            continue
        key = (a[i], b[i])
        if key not in cache:
            cache[key] = SequenceMatcher(None, a[i], b[i]).ratio() < p.get("min_similarity", 0.6)
        flag[i] = cache[key]
    return flag & _base(ctx, p)


def d_round_amounts(ctx, p):
    m = p["modulo"]
    rem = np.mod(ctx.amount, m)
    rounded = (ctx.amount >= p["min_amount"]) & (np.isclose(rem, 0) | np.isclose(rem, m)) & _base(ctx, p)
    _, count = _roll(ctx, p, rounded.astype(float))
    return rounded & (count >= p.get("min_count", 2))


def d_night_activity(ctx, p):
    hour = ctx.df["DATE"].dt.hour.fillna(-1).to_numpy()
    night = (hour >= p["start"]) & (hour < p["end"]) & (ctx.amount >= p["min_amount"]) & _base(ctx, p)
    _, count = ctx.rolling(night.astype(float), p.get("window_h", DAY_H))
    return night & (count >= p.get("min_count", 3))


def d_pep(ctx, p):
    return ctx.cleaned("PPE_SANCTION").isin(TRUTHY).to_numpy()


def d_anj_banned(ctx, p):
    return ctx.cleaned("INTERDIT_ANJ").isin(TRUTHY).to_numpy()


def d_kyc_failure(ctx, p):
    return ctx.cleaned("STATUT_KYC").isin(list(ctx.settings.kyc_failed)).to_numpy()


def d_micro_testing(ctx, p):
    micro = _base(ctx, p) & (ctx.amount <= p["max_amount"]) & (ctx.amount > 0)
    _, count = _roll(ctx, p, micro.astype(float))
    return micro & (count >= p["min_count"])


def d_chargeback(ctx, p):
    keywords = p.get("keywords", ("CHARGEBACK", "IMPAYE", "CONTESTATION", "RETROCESSION",
                                  "OPPOSITION", "LITIGE", "FRAUDE"))
    return ctx.keyword_mask(keywords)


def d_multi_account_ip(ctx, p):
    ip = ctx.df["IP"].astype(str).str.strip()
    valid = ctx.df["IP"].notna() & (ip != "")
    accounts = pd.DataFrame({"ip": ip.where(valid), "c": ctx.client.values}) \
        .groupby("ip")["c"].transform("nunique")
    return (valid & (accounts >= p.get("min_accounts", 3))).to_numpy()


def d_multi_card(ctx, p):
    bins = ctx.df["BIN_CARTE"].astype(str).str.strip()
    valid = ctx.df["BIN_CARTE"].notna() & (bins != "")
    nunique = pd.DataFrame({"b": bins.where(valid), "c": ctx.client.values}) \
        .groupby("c")["b"].transform("nunique")
    return (valid & (nunique >= p.get("min_bins", 4))).to_numpy()


def d_velocity_change(ctx, p):
    base = _base(ctx, p)
    s = pd.Series(np.where(base, ctx.amount, np.nan))
    grp = s.groupby(ctx.client.to_numpy())
    med, cnt = grp.transform("median").to_numpy(), grp.transform("count").to_numpy()
    with np.errstate(invalid="ignore"):
        return base & (cnt >= p.get("min_tx", 5)) & (ctx.amount > p["factor"] * med) & \
            (ctx.amount >= p.get("min_amount", 0))


def d_dormant(ctx, p):
    flag = np.zeros(ctx.n, dtype=bool)
    base = _base(ctx, p)
    for idx in ctx.groups:
        gaps = np.diff(ctx.hours[idx])
        after = idx[np.where(gaps >= p["dormant_days"] * 24)[0] + 1]
        flag[after] = base[after] & (ctx.amount[after] >= p.get("min_amount", 0))
    return flag


def d_cross_flows(ctx, p):
    cp = ctx.cleaned("CONTREPARTIE")
    frame = pd.DataFrame({"k": ctx.client.astype(str).to_numpy() + "|" + cp.to_numpy(),
                          "i": ctx.is_in.astype(int), "o": ctx.is_out.astype(int)})
    grp = frame.groupby("k")
    n_in, n_out = grp["i"].transform("sum"), grp["o"].transform("sum")
    return ((cp != "").to_numpy() & (n_in >= 1).to_numpy() & (n_out >= 1).to_numpy()
            & ((n_in + n_out) >= p.get("min_count", 4)).to_numpy())


def d_large_single(ctx, p):
    return _base(ctx, p) & (ctx.amount >= p["threshold"])


def d_keyword(ctx, p):
    hit = ctx.keyword_mask(p["keywords"]) & _base(ctx, p) & (ctx.amount >= p.get("min_amount", 0))
    _, count = ctx.rolling(hit.astype(float), p.get("window_h", INF))
    return hit & (count >= p.get("min_count", 1))


def d_keyword_early(ctx, p):
    hit = ctx.keyword_mask(p["keywords"]) & _base(ctx, p)
    first = pd.Series(ctx.hours).groupby(ctx.client.to_numpy()).transform("min").to_numpy()
    return hit & ((ctx.hours - first) <= p["early_days"] * 24) & (ctx.hours - first > 0)


def d_shell_company(ctx, p):
    flag = np.zeros(ctx.n, dtype=bool)
    for idx in ctx.groups:
        h = ctx.hours[idx]
        if len(idx) < p["min_ops"] or (h[-1] - h[0]) > p["max_days"] * 24:
            continue
        total_in = ctx.amount[idx][ctx.is_in[idx]].sum()
        total_out = ctx.amount[idx][ctx.is_out[idx]].sum()
        if total_in >= p["min_volume"] and total_out >= p["ratio"] * total_in:
            flag[idx] = True
    return flag


def _fan(ctx, p, direction):
    mask = (ctx.is_in if direction == "in" else ctx.is_out) & (ctx.cleaned("CONTREPARTIE") != "").to_numpy()
    if "max_amount" in p:
        mask &= ctx.amount <= p["max_amount"]
    codes = pd.factorize(ctx.cleaned("CONTREPARTIE"))[0]
    distinct = _rolling_distinct(ctx, mask, codes, p.get("window_h", INF))
    return mask & (distinct >= p["min_counterparties"])


def d_fan_in(ctx, p):
    return _fan(ctx, p, "in")


def d_fan_out(ctx, p):
    return _fan(ctx, p, "out")


def d_multi_country(ctx, p):
    iso = ctx.df["PAYS"].map(to_iso2)
    mask = (iso != "").to_numpy()
    distinct = _rolling_distinct(ctx, mask, pd.factorize(iso)[0], p.get("window_h", INF))
    return mask & (distinct >= p["min_countries"])


def d_repeated_amount(ctx, p):
    mask = ctx.amount >= p["min_amount"]
    keys = ctx.client.astype(str).to_numpy() + "|" + np.round(ctx.amount, 2).astype(str)
    return mask & (_count_by_key(ctx, keys, mask, p.get("window_h", INF)) >= p["min_count"])


def d_mirror_amounts(ctx, p):
    keys = ctx.client.astype(str).to_numpy() + "|" + np.round(ctx.amount, 0).astype(str)
    frame = pd.DataFrame({"k": keys, "i": ctx.is_in.astype(int), "o": ctx.is_out.astype(int),
                          "h": ctx.hours})
    grp = frame.groupby("k")
    n_in, n_out = grp["i"].transform("sum"), grp["o"].transform("sum")
    span = grp["h"].transform("max") - grp["h"].transform("min")
    return ((ctx.amount >= p["min_amount"]) & (n_in >= 1).to_numpy() & (n_out >= 1).to_numpy()
            & ((n_in + n_out) >= p["min_count"]).to_numpy() & (span <= p["window_h"]).to_numpy())


def d_residence_mismatch(ctx, p):
    res = ctx.df["PAYS_RESIDENCE"].map(to_iso2)
    iso = ctx.df["PAYS"].map(to_iso2)
    mism = ((res != "") & (iso != "") & (res != iso)).to_numpy() & (ctx.amount >= p["min_amount"])
    per_client = pd.Series(mism.astype(int)).groupby(ctx.client.to_numpy()).transform("sum").to_numpy()
    return mism & (per_client >= p["min_count"])


def d_missing_keyword(ctx, p):
    hit = ctx.keyword_mask(p["keywords"]) & _base(ctx, p)
    other = ctx.keyword_mask(p["absent_keywords"])
    grp_hit = pd.Series(hit.astype(int)).groupby(ctx.client.to_numpy()).transform("sum").to_numpy()
    grp_other = pd.Series(other.astype(int)).groupby(ctx.client.to_numpy()).transform("sum").to_numpy()
    return hit & (grp_hit >= p["min_count"]) & (grp_other == 0)


def d_new_beneficiary(ctx, p):
    cp = ctx.cleaned("CONTREPARTIE").to_numpy()
    order = np.argsort(ctx.hours, kind="stable")
    keys = pd.Series(ctx.client.astype(str).to_numpy() + "|" + cp)[order]
    first = np.zeros(ctx.n, dtype=bool)
    first[order] = ~keys.duplicated().to_numpy()
    history = np.zeros(ctx.n)
    history[order] = pd.Series(ctx.client.to_numpy()[order]).groupby(ctx.client.to_numpy()[order]).cumcount().to_numpy()
    return (ctx.is_out & (cp != "") & first & (ctx.amount >= p["min_amount"])
            & (history >= p.get("min_history", 5)))


def d_fake_public_rib(ctx, p):
    """Règle 02 : entité publique citée mais pays de l'IBAN incohérent (alerte précalculée)."""
    return np.asarray(ctx.extra["fake_rib"], dtype=bool)


DETECTORS = {
    "pass_through": d_pass_through, "structuring": d_structuring, "cash_cumul": d_cash_cumul,
    "velocity": d_velocity, "high_risk_country": d_high_risk_country, "non_sepa": d_non_sepa,
    "third_party": d_third_party, "round_amounts": d_round_amounts,
    "night_activity": d_night_activity, "pep": d_pep, "kyc_failure": d_kyc_failure,
    "micro_testing": d_micro_testing, "chargeback": d_chargeback,
    "multi_account_ip": d_multi_account_ip, "multi_card": d_multi_card,
    "velocity_change": d_velocity_change, "anj_banned": d_anj_banned, "dormant": d_dormant,
    "cross_flows": d_cross_flows, "large_single": d_large_single, "keyword": d_keyword,
    "keyword_early": d_keyword_early, "tax_haven": d_tax_haven, "shell_company": d_shell_company,
    "fan_in": d_fan_in, "fan_out": d_fan_out, "multi_country": d_multi_country,
    "repeated_amount": d_repeated_amount, "mirror_amounts": d_mirror_amounts,
    "residence_mismatch": d_residence_mismatch, "missing_keyword": d_missing_keyword,
    "new_beneficiary": d_new_beneficiary, "fake_public_rib": d_fake_public_rib,
}


# ---------------------------------------------------------------------------
# Pré-traitement : liste blanche, entités publiques (règles 01 et 02)
# ---------------------------------------------------------------------------
QUAL_WHITELIST = "Exclusion Récurrente Validée"
QUAL_PUBLIC = "Entité publique — vigilance simplifiée"
QUAL_CLIENT = "Client en liste blanche"


def _spaced(series: pd.Series) -> pd.Series:
    """MAJUSCULES, sans accents, séparateurs normalisés en espaces simples."""
    return (series.fillna("").astype(str).str.normalize("NFKD").str.encode("ascii", "ignore")
            .str.decode("ascii").str.upper().str.replace(r"[^A-Z0-9]+", " ", regex=True).str.strip())


def _keyword_mask(spaced: pd.Series, keywords) -> np.ndarray:
    """Correspondance par MOTS ENTIERS (évite que « CAF » corresponde à « CAFETERIA »)."""
    parts = []
    for keyword in keywords:
        k = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", strip_accents(str(keyword)).upper())).strip()
        if k:
            parts.append(re.escape(k))
    if not parts:
        return np.zeros(len(spaced), dtype=bool)
    pattern = r"(?<![A-Z0-9])(?:" + "|".join(parts) + r")(?![A-Z0-9])"
    return spaced.str.contains(pattern, regex=True).to_numpy()


def classify_rows(df: pd.DataFrame, settings: Settings) -> dict:
    """Avant toute détection : opérations neutralisées (liste blanche, entités publiques) et faux RIB."""
    n = len(df)
    empty = pd.Series([""] * n)
    label = _spaced(df["LIBELLE"]) if "LIBELLE" in df.columns else empty
    cparty = _spaced(df["CONTREPARTIE"]) if "CONTREPARTIE" in df.columns else empty
    text = (label + " " + cparty).str.strip()
    country = (df["PAYS_REF"].fillna("").astype(str) if "PAYS_REF" in df.columns else empty).to_numpy()
    high_risk = np.isin(country, list(settings.high_risk))

    pep = np.zeros(n, dtype=bool)
    if "PPE_SANCTION" in df.columns:
        pep = df["PPE_SANCTION"].map(clean_token).isin(TRUTHY).to_numpy()
    cash = np.zeros(n, dtype=bool)
    if "MOYEN_PAIEMENT" in df.columns:
        cash = df["MOYEN_PAIEMENT"].map(clean_token).isin({"CASH", "ESPECES", "ESPECE", "LIQUIDE"}).to_numpy()

    # Règles 01 (exemption) et 02 (faux RIB / usurpation d'entité publique)
    mention = np.zeros(n, dtype=bool)
    expected = np.array([""] * n, dtype=object)
    for entity in settings.public_entities:
        hit = _keyword_mask(text, entity.get("keywords", [])) & ~mention
        mention |= hit
        expected[hit] = str(entity.get("country", "FR")).upper()
    known = country != ""
    exempt_public = mention & known & (country == expected) & ~pep
    fake_rib = mention & known & ((country != expected) | high_risk)

    # Liste blanche : libellé de confiance ET/OU contrepartie / IBAN de confiance
    wl = settings.whitelist_rules
    label_hit = _keyword_mask(label, wl["labels"]) if wl.get("labels") else None
    cp_hit = _keyword_mask(cparty, wl["counterparties"]) if wl.get("counterparties") else None
    if wl.get("ibans") and "IBAN_CONTREPARTIE" in df.columns:
        trusted = {re.sub(r"\s", "", str(i)).upper() for i in wl["ibans"]}
        iban = df["IBAN_CONTREPARTIE"].fillna("").astype(str).str.replace(r"\s", "", regex=True).str.upper()
        iban_hit = iban.isin(trusted).to_numpy()
        cp_hit = iban_hit if cp_hit is None else (cp_hit | iban_hit)
    hits = [h for h in (label_hit, cp_hit) if h is not None]
    if not hits:
        whitelisted = np.zeros(n, dtype=bool)
    elif str(wl.get("mode", "OR")).upper() == "AND":
        whitelisted = np.logical_and.reduce(hits)
    else:
        whitelisted = np.logical_or.reduce(hits)
    # garde-fous : jamais d'exclusion pour PPE / sanctions, espèces, pays à risque ou faux RIB
    whitelisted &= ~(pep | cash | high_risk | fake_rib)

    client_ok = np.zeros(n, dtype=bool)
    if settings.whitelist_ids and "ID_CLIENT" in df.columns:
        client_ok = df["ID_CLIENT"].astype(str).str.strip().isin(settings.whitelist_ids).to_numpy()

    qualification = np.array([""] * n, dtype=object)
    qualification[whitelisted] = QUAL_WHITELIST
    qualification[exempt_public] = QUAL_PUBLIC
    qualification[client_ok] = QUAL_CLIENT
    return {"excluded": exempt_public | whitelisted | client_ok, "fake_rib": fake_rib,
            "qualification": qualification, "public_mentions": int(mention.sum())}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
@dataclass
class AnalysisResult:
    df: pd.DataFrame                 # opérations scorées (toutes, y compris neutralisées)
    flags: dict                      # code typologie -> tableau booléen (aligné sur df)
    typology_status: pd.DataFrame    # couverture + nombre d'alertes
    clients: pd.DataFrame            # profils clients
    codes_to_names: dict
    typologies: dict                 # code -> Typology (typologies actives)
    settings: Settings               # paramétrage appliqué (version, seuils…)


def run_analysis(df: pd.DataFrame, settings: Settings = None) -> AnalysisResult:
    settings = settings or load_settings()
    df = df.reset_index(drop=True)
    total = len(df)
    info = classify_rows(df, settings)
    active_pos = np.flatnonzero(~info["excluded"])
    ctx = None
    if len(active_pos):
        ctx = Ctx(df.iloc[active_pos].reset_index(drop=True), settings)
        ctx.last_n = int(settings.window_n or 0) or None
        ctx.extra = {"fake_rib": info["fake_rib"][active_pos]}

    score = np.zeros(total)
    flags, status = {}, []
    names = {t.code: t.name for t in settings.typologies}
    amount_all = df["MONTANT"].abs().fillna(0.0).to_numpy(dtype=float)

    for t in settings.typologies:
        row = {"Code": t.code, "Typologie": t.name, "Famille": t.family, "Poids": t.weight,
               "Statut": "Évaluée", "Alertes": 0, "Montant concerné": 0.0, "Colonnes manquantes": ""}
        if ctx is None:                       # tout a été neutralisé
            status.append(row)
            continue
        missing = [c for c in required_columns(t) if not ctx.has(c)]
        if missing:
            row["Statut"] = "Non évaluable"
            row["Colonnes manquantes"] = ", ".join(COLUMN_LABELS.get(c, c) for c in missing)
            status.append(row)
            continue
        try:
            part = np.asarray(DETECTORS[t.detector](ctx, t.params), dtype=bool)
        except Exception as exc:  # un détecteur défaillant ne doit pas bloquer l'analyse
            row["Statut"] = "Erreur"
            row["Colonnes manquantes"] = f"{type(exc).__name__}: {exc}"
            status.append(row)
            continue
        full = np.zeros(total, dtype=bool)
        full[active_pos] = part
        flags[t.code] = full
        score += full * t.weight
        row["Alertes"] = int(full.sum())
        row["Montant concerné"] = float(amount_all[full].sum())
        status.append(row)

    out = df.copy()
    out["RISK_SCORE"] = np.minimum(score, settings.cap).round().astype(int)
    out["NIVEAU"] = out["RISK_SCORE"].map(settings.level_for)
    labels = [[] for _ in range(total)]
    for code, flag in flags.items():
        for i in np.flatnonzero(flag):
            labels[i].append(f"{code} {names[code]}")
    out["ALERTES"] = [" | ".join(x) for x in labels]
    out["NB_TYPOLOGIES"] = [len(x) for x in labels]
    out["QUALIFICATION"] = info["qualification"]

    return AnalysisResult(
        df=out, flags=flags, typology_status=pd.DataFrame(status),
        clients=_client_profiles(out, flags, settings), codes_to_names=names,
        typologies={t.code: t for t in settings.typologies}, settings=settings,
    )


def _client_profiles(out: pd.DataFrame, flags: dict, settings: Settings) -> pd.DataFrame:
    client = out["ID_CLIENT"].astype(str).to_numpy() if "ID_CLIENT" in out.columns \
        else np.array(["CLIENT_UNIQUE"] * len(out))
    base = pd.DataFrame({"CLIENT": client, "MONTANT": out["MONTANT"].abs().to_numpy(),
                         "SCORE": out["RISK_SCORE"].to_numpy()})
    grp = base.groupby("CLIENT")
    prof = pd.DataFrame({
        "Opérations": grp.size(),
        "Volume": grp["MONTANT"].sum(),
        "Score max": grp["SCORE"].max(),
    })
    if flags:
        fdf = pd.DataFrame(flags)
        fdf["CLIENT"] = client
        any_by = fdf.groupby("CLIENT").any()
        prof["Typologies distinctes"] = any_by.sum(axis=1)
        prof["Typologies"] = any_by.apply(lambda r: ", ".join(r.index[r.to_numpy()]), axis=1)
    else:
        prof["Typologies distinctes"] = 0
        prof["Typologies"] = ""
    bonus = (prof["Typologies distinctes"] - 1).clip(lower=0) * settings.diversity_bonus
    prof["Score client"] = np.minimum(prof["Score max"] + bonus, settings.cap).astype(int)
    prof["Niveau"] = prof["Score client"].map(settings.level_for)
    prof = prof.reset_index().rename(columns={"CLIENT": "Client"})
    return prof.sort_values(["Score client", "Volume"], ascending=False).reset_index(drop=True)
