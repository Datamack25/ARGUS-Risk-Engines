"""Configuration globale d'Argus RISK (valeurs par défaut).

Les valeurs modifiables par le Head of Compliance (seuils, poids, listes, fenêtre N, liste blanche…)
sont surchargées par config/rules.json via core/settings.py (page Administration).
"""

APP_NAME = "Argus RISK"
APP_TITLE = "Argus RISK : Analyse de transaction"
APP_SUBTITLE = "Analyse transactionnelle — Rapport LCB-FT & Fraude"
VERSION = "2.2.0"
LAST_UPDATE = "2026-10"
AUTHOR = "Mackenson CINEUS"

# --- Scoring (valeurs par défaut) --------------------------------------------
SCORE_CAP = 100          # score maximum d'une opération
THRESHOLD_N1 = 40        # >= : alerte modérée (analyse N1)
THRESHOLD_N2 = 70        # >= : escalade N2 (dossier d'investigation)

# Fenêtre courte : les détecteurs comportementaux (fractionnement, rebond, vélocité…) examinent
# en priorité les N dernières transactions du client (0 = désactivée).
WINDOW_N = 5

LEVEL_LOW = "Faible"
LEVEL_N1 = "Modéré (N1)"
LEVEL_N2 = "Élevé (N2)"
LEVELS = [LEVEL_LOW, LEVEL_N1, LEVEL_N2]

# Bonus appliqué au score d'un client par typologie distincte supplémentaire
CLIENT_DIVERSITY_BONUS = 5

# --- Filtrage des opérations techniques (bruit de fond) ------------------------
# Une opération dont le libellé (nettoyé : MAJUSCULES, sans accents ni espaces)
# contient l'un de ces mots est ignorée par le moteur.
EXCLUSIONS = [
    "REJET", "RESTITUTION", "MAINLEVEE", "TVA", "COMMISSION", "FRAIS",
    "TCION", "AGIOS", "TAXE", "AJUSTEMENT",
]


def level_for(score: float) -> str:
    """Niveau de risque selon les seuils PAR DÉFAUT (le moteur utilise ceux de Settings)."""
    if score >= THRESHOLD_N2:
        return LEVEL_N2
    if score >= THRESHOLD_N1:
        return LEVEL_N1
    return LEVEL_LOW
