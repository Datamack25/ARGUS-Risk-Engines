"""Catalogue unique des typologies de fraude, blanchiment et LCB-FT (47 typologies).

Sources d'inspiration : bibliothèques de scénarios des plateformes de référence
(NICE Actimize, SAS AML, Oracle FCCM, Feedzai, Quantexa, Verafin, Hawk AI :
règles + comportement + analyse de réseaux), rapports de typologies TRACFIN
(travail dissimulé, fraude fiscale et sociale, sociétés éphémères « taxis »,
fraude aux aides publiques / CPF, abus de biens sociaux) et indicateurs GAFI.

Les POIDS et paramètres définis ici sont les valeurs PAR DÉFAUT : ils peuvent être surchargés sans
toucher au code via la page Administration (config/rules.json, voir core/settings.py). Pour modifier un seuil ou ajouter une typologie,
éditer ce fichier (voir l'onglet « Mettre à jour » du guide).
"""

from dataclasses import dataclass, field

DAY = 24            # heures
CASH = ("CASH", "ESPECES", "ESPECE", "LIQUIDE")

FAMILIES = {
    "LCB": "Blanchiment & LCB-FT",
    "FRA": "Fractionnement & espèces",
    "SAN": "Sanctions, PPE & juridictions",
    "FIS": "Fraude fiscale & sociale",
    "TRA": "Travail illégal / dissimulé",
    "FRD": "Fraude aux moyens de paiement & escroquerie",
    "SEC": "Risques sectoriels (jeux, assurance)",
    "CUS": "Typologies personnalisées (Admin)",
}


@dataclass(frozen=True)
class Typology:
    code: str
    name: str
    weight: int
    signal: str
    detector: str
    params: dict = field(default_factory=dict)

    @property
    def family(self) -> str:
        return FAMILIES[self.code.split("-")[0]]


def T(code, name, weight, signal, detector, **params):
    return Typology(code, name, weight, signal, detector, params)


# Colonnes logiques requises par détecteur (MONTANT est toujours requis).
DETECTOR_REQUIRES = {
    "pass_through": ["SENS"], "structuring": [], "cash_cumul": ["MOYEN_PAIEMENT"],
    "velocity": [], "high_risk_country": ["PAYS"], "non_sepa": ["PAYS"], "tax_haven": ["PAYS"],
    "third_party": ["NOM_CLIENT", "NOM_TITULAIRE_COMPTE"], "round_amounts": [],
    "night_activity": ["HEURE"], "pep": ["PPE_SANCTION"], "kyc_failure": ["STATUT_KYC"],
    "micro_testing": [], "chargeback": ["TEXTE"], "multi_account_ip": ["IP", "CLIENT"],
    "multi_card": ["BIN_CARTE", "CLIENT"], "velocity_change": ["CLIENT"],
    "anj_banned": ["INTERDIT_ANJ"], "dormant": ["DATE", "CLIENT"],
    "cross_flows": ["CONTREPARTIE", "SENS"], "large_single": [], "keyword": ["TEXTE"],
    "keyword_early": ["TEXTE", "DATE", "CLIENT"], "shell_company": ["DATE", "CLIENT", "SENS"],
    "fan_in": ["CONTREPARTIE", "SENS"], "fan_out": ["CONTREPARTIE", "SENS"],
    "multi_country": ["PAYS"], "repeated_amount": [], "mirror_amounts": ["SENS", "DATE"],
    "residence_mismatch": ["PAYS_RESIDENCE", "PAYS", "CLIENT"],
    "missing_keyword": ["TEXTE", "CLIENT"],
    "new_beneficiary": ["CONTREPARTIE", "SENS", "DATE", "CLIENT"],
    "fake_public_rib": ["TEXTE", "PAYS_REF"],
}

COLUMN_LABELS = {
    "SENS": "Sens (SENS ou TYPE_OPERATION)", "MOYEN_PAIEMENT": "MOYEN_PAIEMENT", "PAYS": "PAYS",
    "PAYS_RESIDENCE": "PAYS_RESIDENCE", "NOM_CLIENT": "NOM_CLIENT",
    "NOM_TITULAIRE_COMPTE": "NOM_TITULAIRE_COMPTE", "HEURE": "DATE avec heure", "DATE": "DATE",
    "PPE_SANCTION": "PPE_SANCTION", "STATUT_KYC": "STATUT_KYC",
    "TEXTE": "LIBELLE / STATUT / TYPE_OPERATION", "IP": "IP", "CLIENT": "ID_CLIENT (ou NOM_CLIENT)",
    "BIN_CARTE": "BIN_CARTE", "INTERDIT_ANJ": "INTERDIT_ANJ", "CONTREPARTIE": "CONTREPARTIE",
    "CANAL": "CANAL", "PAYS_REF": "PAYS ou IBAN_CONTREPARTIE",
}


def required_columns(t: Typology) -> list:
    """Colonnes logiques nécessaires pour évaluer une typologie."""
    req = list(DETECTOR_REQUIRES.get(t.detector, []))
    p = t.params
    extra = []
    if p.get("direction"):
        extra.append("SENS")
    if "methods" in p:
        extra.append("MOYEN_PAIEMENT")
    if "channels" in p:
        extra.append("CANAL")
    if "window_h" in p and "HEURE" not in req:
        extra.append("DATE")
    if "credit_keywords" in p or "absent_keywords" in p:
        extra.append("TEXTE")
    return req + [c for c in extra if c not in req]


TYPOLOGIES = (
    # ------------------------------------------------------------------ LCB
    T("LCB-01", "Passage rapide de fonds (pass-through)", 35,
      "Crédit important suivi d'un débit quasi équivalent en moins de 48 h.",
      "pass_through", window_h=2 * DAY, min_amount=3000, ratio=0.85),
    T("LCB-02", "Société éphémère / « lessiveuse »", 35,
      "Structure récente (< 90 jours) au volume élevé dont les sorties reprennent ≥ 90 % des entrées.",
      "shell_company", max_days=90, min_ops=8, min_volume=20000, ratio=0.9),
    T("LCB-03", "Compte de collecte (nombreux donneurs d'ordre)", 30,
      "8 contreparties distinctes ou plus créditent le même compte en 7 jours.",
      "fan_in", min_counterparties=8, window_h=7 * DAY),
    T("LCB-04", "Dispersion rapide de fonds (nombreux bénéficiaires)", 25,
      "8 bénéficiaires distincts ou plus en 7 jours.",
      "fan_out", min_counterparties=8, window_h=7 * DAY),
    T("LCB-05", "Multi-virements rapides", 20,
      "5 virements émis ou plus en 24 h.",
      "velocity", min_count=5, window_h=DAY, direction="out",
      methods=("VIR_SEPA", "VIR_INST", "VIREMENT", "VIR")),
    T("LCB-06", "Flux croisés / allers-retours", 25,
      "Allers-retours répétés avec une même contrepartie sans justification économique.",
      "cross_flows", min_count=4),
    T("LCB-07", "Réactivation d'un compte dormant", 25,
      "Opération ≥ 5 000 € après 180 jours sans activité.",
      "dormant", dormant_days=180, min_amount=5000),
    T("LCB-08", "Opération immobilière atypique", 20,
      "Flux ≥ 50 000 € libellé acquisition, notaire, SCI ou immobilier.",
      "keyword", keywords=("NOTAIRE", "IMMOBILIER", "ACQUISITION", "SCI", "COMPROMIS"),
      min_amount=50000),
    T("LCB-09", "Structures opaques (trust, holding, offshore)", 20,
      "Opération impliquant un trust, une fondation, une holding, un nominee ou une structure offshore.",
      "keyword", keywords=("TRUST", "FONDATION", "OFFSHORE", "NOMINEE", "SPV", "FIDUCIAIRE", "HOLDING")),
    T("LCB-10", "Exposition aux cryptoactifs", 15,
      "Flux ≥ 1 000 € vers ou depuis une plateforme de cryptoactifs.",
      "keyword", keywords=("CRYPTO", "BITCOIN", "BINANCE", "COINBASE", "USDT", "KRAKEN"),
      min_amount=1000),
    T("LCB-11", "Opération unitaire atypique", 20,
      "Opération unitaire ≥ 50 000 €.",
      "large_single", threshold=50000),
    T("LCB-12", "Rupture d'habitude (montant)", 15,
      "Montant supérieur à 5 fois le montant médian du client (≥ 5 opérations d'historique).",
      "velocity_change", factor=5, min_tx=5, min_amount=1000),
    T("LCB-13", "Multiplicité de pays en peu de temps", 20,
      "4 pays distincts ou plus en 7 jours.",
      "multi_country", min_countries=4, window_h=7 * DAY),
    # ------------------------------------------------------------------ FRA
    T("FRA-01", "Fractionnement d'espèces sous 10 000 €", 25,
      "3 opérations d'espèces ou plus entre 80 % et 100 % du seuil de 10 000 € en 7 jours.",
      "structuring", threshold=10000, band_low=0.8, min_count=3, window_h=7 * DAY, methods=CASH),
    T("FRA-02", "Fractionnement sous le seuil de 3 000 €", 20,
      "4 opérations ou plus juste sous 3 000 € en 72 h.",
      "structuring", threshold=3000, band_low=0.85, min_count=4, window_h=3 * DAY),
    T("FRA-03", "Montants identiques répétés", 15,
      "4 opérations identiques de plus de 500 € en 30 jours.",
      "repeated_amount", min_amount=500, min_count=4, window_h=30 * DAY),
    T("FRA-04", "Concentration de montants ronds", 15,
      "Montants ronds élevés répétés (≥ 5 000 €, multiples de 1 000 €).",
      "round_amounts", min_amount=5000, modulo=1000, min_count=2, window_h=30 * DAY),
    T("FRA-05", "Espèces cumulées atypiques", 30,
      "Flux d'espèces cumulés ≥ 8 000 € sur 30 jours.",
      "cash_cumul", threshold=8000, window_h=30 * DAY, methods=CASH),
    # ------------------------------------------------------------------ SAN
    T("SAN-01", "Correspondance PPE / sanctions", 50,
      "Lien détecté avec une liste de sanctions ou une personne exposée politiquement.",
      "pep"),
    T("SAN-02", "Flux liés à une juridiction à haut risque", 30,
      "Opération avec un pays figurant dans la liste de surveillance.",
      "high_risk_country"),
    T("SAN-03", "Paiements hors zone SEPA", 15,
      "Opération avec un pays hors SEPA.",
      "non_sepa"),
    T("SAN-04", "Petits transferts répétés vers zones à risque (FT)", 35,
      "3 transferts de moins de 1 000 € ou plus vers une juridiction à risque en 30 jours.",
      "high_risk_country", max_amount=1000, min_count=3, window_h=30 * DAY),
    # ------------------------------------------------------------------ FIS
    T("FIS-01", "Flux vers territoires à fiscalité privilégiée", 25,
      "Opération avec un centre offshore ou un territoire à fiscalité privilégiée.",
      "tax_haven"),
    T("FIS-02", "Dépôts d'espèces récurrents (revenus non déclarés)", 20,
      "6 dépôts d'espèces ou plus en 30 jours.",
      "velocity", min_count=6, window_h=30 * DAY, direction="in", methods=CASH),
    T("FIS-03", "Facturation circulaire (montants miroirs)", 25,
      "Mêmes montants reçus puis restitués (≥ 4 opérations, ≥ 1 000 €) en 7 jours.",
      "mirror_amounts", min_amount=1000, min_count=4, window_h=7 * DAY),
    T("FIS-04", "Incohérence de résidence fiscale", 20,
      "3 opérations ≥ 1 000 € ou plus dans un pays autre que la résidence déclarée.",
      "residence_mismatch", min_amount=1000, min_count=3),
    T("FIS-05", "Prélèvements atypiques du dirigeant (abus de biens sociaux)", 20,
      "3 sorties ou plus libellées compte courant d'associé, dirigeant ou prélèvement personnel en 90 jours.",
      "keyword", keywords=("COMPTECOURANT", "ASSOCIE", "DIRIGEANT", "PRELEVEMENTPERSONNEL"),
      min_count=3, window_h=90 * DAY, direction="out"),
    T("FIS-06", "Fraude aux aides publiques (CPF, rénovation, chômage partiel)", 30,
      "Aide publique reçue puis reversée à ≥ 90 % en 7 jours.",
      "pass_through", window_h=7 * DAY, min_amount=1000, ratio=0.9,
      credit_keywords=("CPF", "MONCOMPTEFORMATION", "CAISSEDESDEPOTS", "PRIMERENOV",
                       "CHOMAGEPARTIEL", "SUBVENTION", "FRANCETRAVAIL", "POLEEMPLOI")),
    # ------------------------------------------------------------------ TRA
    T("TRA-01", "Salaires versés en espèces", 25,
      "3 paiements de salaire ou de main-d'œuvre en espèces ou plus en 30 jours.",
      "keyword", keywords=("SALAIRE", "PAIEOUVRIER", "PAIESALARIE", "MAINDOEUVRE", "OUVRIER", "REMUNERATION"),
      min_count=3, window_h=30 * DAY, direction="out", methods=CASH),
    T("TRA-02", "Paie informelle (virements modestes à nombreux bénéficiaires)", 25,
      "6 bénéficiaires distincts ou plus reçoivent chacun moins de 1 500 € en 30 jours.",
      "fan_out", min_counterparties=6, window_h=30 * DAY, max_amount=1500),
    T("TRA-03", "Salaires sans cotisations sociales", 30,
      "Salaires versés sans aucun règlement URSSAF/DSN/cotisations dans le fichier.",
      "missing_keyword", keywords=("SALAIRE", "PAIEOUVRIER", "PAIESALARIE", "OUVRIER"),
      absent_keywords=("URSSAF", "COTISATION", "DSN", "CAISSERETRAITE", "MSA"),
      min_count=3, direction="out"),
    T("TRA-04", "Retraits d'espèces importants (paie informelle)", 20,
      "Retraits d'espèces cumulés ≥ 3 000 € en 7 jours.",
      "cash_cumul", threshold=3000, window_h=7 * DAY, methods=CASH, direction="out"),
    # ------------------------------------------------------------------ FRD
    T("FRD-01", "Test de cartes (micro-paiements)", 30,
      "5 opérations de moins de 10 € ou plus en 2 h.",
      "micro_testing", max_amount=10, min_count=5, window_h=2),
    T("FRD-02", "Chargeback / impayé / contestation", 30,
      "Paiements suivis d'impayés, de contestations ou de chargebacks.",
      "chargeback"),
    T("FRD-03", "Multi-comptes sur une même adresse IP", 25,
      "3 comptes distincts ou plus depuis la même adresse IP.",
      "multi_account_ip", min_accounts=3),
    T("FRD-04", "Multi-cartes sur un même compte", 25,
      "4 BIN de cartes différents ou plus alimentant un même compte.",
      "multi_card", min_bins=4),
    T("FRD-05", "Paiement vers un compte de tiers", 35,
      "Titulaire du compte bénéficiaire différent du client.",
      "third_party", direction="out"),
    T("FRD-06", "Défaillance KYC / anomalie documentaire", 25,
      "Dossier client incomplet, expiré, rejeté ou document invalide.",
      "kyc_failure"),
    T("FRD-07", "Nouveau bénéficiaire important (fraude au président)", 30,
      "Premier virement ≥ 10 000 € vers un nouveau bénéficiaire, sur un compte à l'historique établi.",
      "new_beneficiary", min_amount=10000, min_history=5),
    T("FRD-08", "Pics d'activité nocturne", 10,
      "3 opérations ≥ 500 € ou plus entre 02h00 et 05h00 sur 24 h.",
      "night_activity", start=2, end=5, min_amount=500, min_count=3, window_h=DAY),
    T("FRD-09", "Remises de chèques répétées", 15,
      "5 remises de chèques ou plus en 7 jours.",
      "keyword", keywords=("REMISECHEQUE", "REMISECHQ", "CHQ"), min_count=5,
      window_h=7 * DAY, direction="in"),
    T("FRD-10", "Usurpation d'entité publique / faux RIB", 95,
      "Libellé ou contrepartie citant une administration (URSSAF, DGFiP…) mais IBAN d'un autre pays ou d'une juridiction à risque.",
      "fake_public_rib"),
    # ------------------------------------------------------------------ SEC
    T("SEC-01", "Jeux : recharges compulsives (chasse aux pertes)", 20,
      "5 recharges ou plus en moins de 2 h.",
      "velocity", min_count=5, window_h=2, direction="in"),
    T("SEC-02", "Jeux : joueur inscrit au fichier des interdits", 40,
      "Client présent au fichier national des interdits de jeux.",
      "anj_banned"),
    T("SEC-03", "Jeux : abus de bonus", 15,
      "Retrait rapide après crédit de bonus ou de promotion.",
      "pass_through", window_h=3 * DAY, min_amount=20, ratio=0.5,
      credit_keywords=("BONUS", "PROMO", "FREEBET")),
    T("SEC-04", "Assurance : rachat ou résiliation anticipés", 30,
      "Rachat, résiliation ou renonciation dans les 90 jours suivant la souscription.",
      "keyword_early", keywords=("RACHAT", "RESILIATION", "RENONCIATION"), early_days=90),
    T("SEC-05", "Assurance : sinistres répétés", 20,
      "3 sinistres ou indemnisations ou plus en 12 mois.",
      "keyword", keywords=("SINISTRE", "INDEMNISATION"), min_count=3, window_h=365 * DAY),
)

assert len({t.code for t in TYPOLOGIES}) == len(TYPOLOGIES) >= 30, "Au moins 30 typologies uniques."
