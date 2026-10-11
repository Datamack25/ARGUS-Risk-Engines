"""Constats de l'analyse : paragraphe de synthèse rédigé + tableau des transactions suspectes."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as cfg
from .engine import AnalysisResult
from .typologies import FAMILIES


def fmt_eur(value: float) -> str:
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


@dataclass
class Findings:
    headline: str            # phrase d'ouverture (verdict)
    summary: str             # paragraphe de synthèse
    details: list            # un paragraphe par typologie déclenchée (ordre d'importance)
    clients_paragraph: str   # clients les plus exposés
    limits: str              # limites / typologies non évaluables
    table: pd.DataFrame      # transactions suspectes


def _ids(sub: pd.DataFrame, limit: int = 6) -> str:
    col = "ID_TRANSACTION" if "ID_TRANSACTION" in sub.columns else None
    values = (sub[col].astype(str) if col else sub.index.map(lambda i: f"ligne {i + 2}").astype(str)).tolist()
    text = ", ".join(values[:limit])
    return text + (f" … (+{len(values) - limit})" if len(values) > limit else "")


def _names(sub: pd.DataFrame, limit: int = 3) -> str:
    col = "NOM_CLIENT" if "NOM_CLIENT" in sub.columns else "ID_CLIENT"
    if col not in sub.columns:
        return "le compte analysé"
    values = sub[col].astype(str).value_counts().index.tolist()
    text = ", ".join(values[:limit])
    return text + (f" et {len(values) - limit} autre(s)" if len(values) > limit else "")


def _cparties(sub: pd.DataFrame, limit: int = 3) -> str:
    """Contreparties concernées avec leur IBAN (texte), si disponibles."""
    cp = sub["CONTREPARTIE"] if "CONTREPARTIE" in sub.columns else pd.Series("", index=sub.index)
    ib = sub["IBAN_CONTREPARTIE"] if "IBAN_CONTREPARTIE" in sub.columns else pd.Series("", index=sub.index)
    pairs = []
    for name, iban in zip(cp.fillna("").astype(str), ib.fillna("").astype(str)):
        name, iban = name.strip(), iban.strip()
        if not (name or iban):
            continue
        label = f"{name} (IBAN {iban})" if name and iban and name.replace(" ", "").upper() != iban.replace(" ", "").upper() \
            else (f"IBAN {iban}" if iban else name)
        if label not in pairs:
            pairs.append(label)
    if not pairs:
        return ""
    text = "; ".join(pairs[:limit])
    return text + (f" et {len(pairs) - limit} autre(s)" if len(pairs) > limit else "")


def suspicious_table(res: AnalysisResult) -> pd.DataFrame:
    """Toutes les opérations ayant déclenché au moins une typologie, triées par score."""
    df = res.df
    sub = df[df["NB_TYPOLOGIES"] > 0].copy()
    cols = [c for c in ["ID_TRANSACTION", "DATE", "ID_CLIENT", "NOM_CLIENT", "LIBELLE", "CONTREPARTIE",
                        "IBAN_CONTREPARTIE", "MONTANT", "SENS", "PAYS", "RISK_SCORE", "NIVEAU", "ALERTES",
                        "FICHIER_SOURCE"] if c in sub.columns]
    sub = sub.sort_values(["RISK_SCORE", "MONTANT"], ascending=False)
    return sub[cols].rename(columns={"ALERTES": "POURQUOI (typologies détectées)"})


def build_findings(res: AnalysisResult, source: str) -> Findings:
    df = res.df
    flagged = df[df["NB_TYPOLOGIES"] > 0]
    n2 = int((df["NIVEAU"] == cfg.LEVEL_N2).sum())
    n1 = int((df["NIVEAU"] == cfg.LEVEL_N1).sum())
    clients_flagged = int(flagged["ID_CLIENT"].nunique()) if "ID_CLIENT" in flagged.columns and len(flagged) else 0
    evaluated = res.typology_status[res.typology_status["Statut"] == "Évaluée"]
    triggered = evaluated[evaluated["Alertes"] > 0]

    # --- verdict et synthèse --------------------------------------------------
    if len(flagged) == 0:
        headline = "Aucune opération suspecte n'a été relevée."
        summary = (f"L'analyse du fichier « {source} » ({len(df)} opérations, {fmt_eur(df['MONTANT'].sum())}) "
                   f"n'a déclenché aucune des {len(evaluated)} typologies évaluées.")
    else:
        level = ("des opérations à escalader en N2" if n2 else
                 "des opérations à examiner en N1" if n1 else "des signaux faibles")
        headline = f"{len(flagged)} opération(s) suspecte(s) relevée(s) — {level}."
        fam_counts = (triggered.groupby("Famille")["Alertes"].sum().sort_values(ascending=False))
        fam_text = ", ".join(f"{fam} ({int(n)} alerte(s))" for fam, n in fam_counts.head(4).items())
        summary = (
            f"L'analyse du fichier « {source} » porte sur {len(df)} opérations pour un volume de "
            f"{fmt_eur(df['MONTANT'].sum())}. Le moteur a évalué {len(evaluated)} typologies sur "
            f"{len(res.typology_status)} et en a déclenché {len(triggered)}. Il relève "
            f"{len(flagged)} opération(s) suspecte(s), représentant {fmt_eur(flagged['MONTANT'].sum())} "
            f"et concernant {clients_flagged} client(s) : {n2} au niveau d'escalade N2 "
            f"(score ≥ {res.settings.n2}) et {n1} au niveau modéré N1 (score ≥ {res.settings.n1}). "
            f"Les familles de risque dominantes sont : {fam_text}."
        )

    # --- un paragraphe par typologie -----------------------------------------
    details = []
    ranked = triggered.assign(_score=triggered["Poids"] * 1000 + triggered["Alertes"]) \
        .sort_values("_score", ascending=False)
    for _, row in ranked.iterrows():
        code = row["Code"]
        sub = df[res.flags[code]]
        t = res.typologies[code]
        cps = _cparties(sub)
        details.append(
            f"**{code} — {t.name}** ({row['Famille']}) : {len(sub)} opération(s) pour "
            f"{fmt_eur(sub['MONTANT'].sum())}, concernant {_names(sub)}. {t.signal} "
            f"Opérations concernées : {_ids(sub)}."
            + (f" Contrepartie(s) concernée(s) : {cps}." if cps else "")
        )

    # --- clients les plus exposés ---------------------------------------------
    top = res.clients[res.clients["Niveau"] != cfg.LEVEL_LOW].head(5)
    if len(top):
        parts = [f"{r['Client']} (score {int(r['Score client'])}, {int(r['Typologies distinctes'])} typologie(s), "
                 f"{fmt_eur(r['Volume'])})" for _, r in top.iterrows()]
        clients_paragraph = "Clients les plus exposés : " + " ; ".join(parts) + "."
    else:
        clients_paragraph = "Aucun client n'atteint le niveau modéré."

    # --- limites -----------------------------------------------------------------
    skipped = res.typology_status[res.typology_status["Statut"] != "Évaluée"]
    if len(skipped):
        limits = (f"{len(skipped)} typologie(s) sur {len(res.typology_status)} n'ont pas pu être évaluées "
                  f"faute de colonnes (voir « Couverture » dans le Rapport Synthèse) : l'absence d'alerte "
                  f"sur ces typologies ne vaut pas absence de risque.")
    else:
        limits = "Toutes les typologies du catalogue ont pu être évaluées."

    return Findings(headline, summary, details, clients_paragraph, limits, suspicious_table(res))
