"""Listes de référence (pays, valeurs booléennes, statuts KYC).

⚠️ MAINTENANCE : ces listes évoluent. Après chaque publication du GAFI/FATF
(plénières habituellement en février, juin et octobre) et de la Commission
européenne (pays tiers à haut risque), mettre à jour HIGH_RISK_COUNTRIES et
renseigner REFERENCE_LISTS_REVIEWED. Voir l'onglet « Mise à jour » du guide.
"""

import re
import unicodedata

# Date de la dernière vérification humaine des listes ci-dessous.
# À RENSEIGNER lors de la validation par la conformité.
REFERENCE_LISTS_REVIEWED = "À renseigner (liste de travail à valider avant usage en production)"

# Pays de la zone SEPA (codes ISO 3166-1 alpha-2), DOM-COM français inclus.
SEPA_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO", "CH", "MC", "SM", "VA", "AD", "GB",
    "GP", "MQ", "RE", "GF", "YT", "PM", "BL", "MF",
}

# Juridictions à surveiller : liste de TRAVAIL, à confronter aux dernières
# publications officielles (GAFI : liste noire / liste grise, UE).
HIGH_RISK_COUNTRIES = {
    # Appel à l'action (liste noire)
    "KP": "Corée du Nord", "IR": "Iran", "MM": "Myanmar",
    # Surveillance renforcée (liste grise) — instantané de travail
    "DZ": "Algérie", "AO": "Angola", "BO": "Bolivie", "BG": "Bulgarie",
    "BF": "Burkina Faso", "CM": "Cameroun", "CI": "Côte d'Ivoire",
    "CD": "RD Congo", "HT": "Haïti", "KE": "Kenya", "LA": "Laos",
    "LB": "Liban", "MC": "Monaco", "MZ": "Mozambique", "NA": "Namibie",
    "NP": "Népal", "NG": "Nigéria", "ZA": "Afrique du Sud", "SS": "Soudan du Sud",
    "SY": "Syrie", "VE": "Venezuela", "VN": "Vietnam", "VG": "Îles Vierges britanniques",
    "YE": "Yémen",
}

# Territoires à fiscalité privilégiée / centres offshore : liste de TRAVAIL à valider
# (liste UE des juridictions non coopératives, listes OCDE, politique interne).
TAX_HAVENS = {
    "KY": "Îles Caïmans", "VG": "Îles Vierges britanniques", "BS": "Bahamas", "BZ": "Belize",
    "PA": "Panama", "SC": "Seychelles", "VU": "Vanuatu", "BM": "Bermudes", "AI": "Anguilla",
    "TC": "Îles Turques-et-Caïques", "WS": "Samoa", "MH": "Îles Marshall", "AG": "Antigua-et-Barbuda",
}

# Noms de pays usuels -> code ISO2 (pour les fichiers qui n'ont pas de codes).
_NAMES = [
    ("FR", "FRANCE"), ("DE", "ALLEMAGNE|GERMANY"), ("ES", "ESPAGNE|SPAIN"),
    ("IT", "ITALIE|ITALY"), ("BE", "BELGIQUE|BELGIUM"), ("NL", "PAYSBAS|NETHERLANDS"),
    ("LU", "LUXEMBOURG"), ("PT", "PORTUGAL"), ("IE", "IRLANDE|IRELAND"),
    ("AT", "AUTRICHE|AUSTRIA"), ("FI", "FINLANDE|FINLAND"), ("GR", "GRECE|GREECE"),
    ("MT", "MALTE|MALTA"), ("CY", "CHYPRE|CYPRUS"), ("PL", "POLOGNE|POLAND"),
    ("RO", "ROUMANIE|ROMANIA"), ("BG", "BULGARIE|BULGARIA"), ("HU", "HONGRIE|HUNGARY"),
    ("CZ", "TCHEQUIE|CZECHIA"), ("DK", "DANEMARK|DENMARK"), ("SE", "SUEDE|SWEDEN"),
    ("GB", "ROYAUMEUNI|UNITEDKINGDOM|UK"), ("CH", "SUISSE|SWITZERLAND"),
    ("NO", "NORVEGE|NORWAY"), ("MC", "MONACO"), ("GP", "GUADELOUPE"),
    ("MQ", "MARTINIQUE"), ("RE", "REUNION|LAREUNION"), ("GF", "GUYANE"),
    ("YT", "MAYOTTE"), ("MA", "MAROC|MOROCCO"), ("DZ", "ALGERIE|ALGERIA"),
    ("TN", "TUNISIE|TUNISIA"), ("SN", "SENEGAL"), ("CI", "COTEDIVOIRE|IVORYCOAST"),
    ("CM", "CAMEROUN|CAMEROON"), ("NG", "NIGERIA"), ("HT", "HAITI"),
    ("CD", "RDCONGO|RDC|CONGORDC"), ("ML", "MALI"), ("BF", "BURKINAFASO"),
    ("GN", "GUINEE|GUINEA"), ("TG", "TOGO"), ("BJ", "BENIN"), ("GA", "GABON"),
    ("MG", "MADAGASCAR"), ("MU", "MAURICE|MAURITIUS"), ("JM", "JAMAIQUE|JAMAICA"),
    ("DO", "REPUBLIQUEDOMINICAINE"), ("US", "ETATSUNIS|USA|UNITEDSTATES"),
    ("CN", "CHINE|CHINA"), ("RU", "RUSSIE|RUSSIA"), ("TR", "TURQUIE|TURKEY"),
    ("AE", "EMIRATSARABESUNIS|EAU|UAE|DUBAI"), ("IR", "IRAN"), ("KP", "COREEDUNORD"),
    ("MM", "MYANMAR|BIRMANIE"), ("SY", "SYRIE|SYRIA"), ("YE", "YEMEN"),
    ("SS", "SOUDANDUSUD"), ("VE", "VENEZUELA"), ("LB", "LIBAN|LEBANON"),
    ("KE", "KENYA"), ("VN", "VIETNAM"), ("ZA", "AFRIQUEDUSUD|SOUTHAFRICA"),
    ("PA", "PANAMA"), ("KY", "ILESCAIMANS|CAYMANISLANDS"), ("BS", "BAHAMAS"),
    ("VG", "ILESVIERGESBRITANNIQUES"), ("SC", "SEYCHELLES"), ("BM", "BERMUDES|BERMUDA"),
]
NAME_TO_ISO2 = {n: code for code, names in _NAMES for n in names.split("|")}

# Valeurs interprétées comme « vrai » dans les colonnes PPE_SANCTION / INTERDIT_ANJ
TRUTHY = {"OUI", "O", "YES", "Y", "TRUE", "VRAI", "1", "PPE", "PEP", "SANCTION", "MATCH", "HIT"}

# Statuts KYC considérés comme défaillants
KYC_FAILED = {
    "KO", "ECHEC", "ECHOUE", "REJETE", "REFUSE", "EXPIRE", "INCOMPLET",
    "SUSPENDU", "FAILED", "REJECTED", "EXPIRED", "INVALID", "INVALIDE", "NONVERIFIE",
}

# Mots-clés de dénomination sociale ou civilité ignorés pour comparer les noms
NAME_STOPWORDS = {"M", "MR", "MME", "MLLE", "MONSIEUR", "MADAME", "MADEMOISELLE",
                  "SARL", "SAS", "SASU", "SA", "EURL", "SCI"}


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def clean_token(text) -> str:
    """MAJUSCULES, sans accents, uniquement A-Z0-9."""
    if text is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", strip_accents(str(text)).upper())


def to_iso2(value) -> str:
    """Convertit un pays (code ou nom) en code ISO2. Retourne '' si inconnu."""
    token = clean_token(value)
    if not token:
        return ""
    if len(token) == 2 and token.isalpha():
        return token
    return NAME_TO_ISO2.get(token, "")


# Libellés de confiance par défaut (liste blanche : paiements récurrents). Modifiables dans Administration.
DEFAULT_WHITELIST_LABELS = ["LOYER", "IMPOT", "TAXE FONCIERE", "ASSURANCE HABITATION", "ABONNEMENT", "MUTUELLE"]

# Référentiel des entités publiques légitimes (vigilance simplifiée si le pays de l'IBAN correspond ;
# alerte « faux RIB / usurpation » sinon). Les mots-clés sont comparés par MOTS ENTIERS.
DEFAULT_PUBLIC_ENTITIES = [
    {"name": "DGFiP / Trésor public / Impôts", "keywords": ["DGFIP", "DGFP", "TRESOR PUBLIC", "SERVICE DES IMPOTS", "SIE"], "country": "FR"},
    {"name": "Douanes", "keywords": ["DOUANE", "DOUANES", "DGDDI"], "country": "FR"},
    {"name": "Caisse des dépôts", "keywords": ["CAISSE DES DEPOTS"], "country": "FR"},
    {"name": "Bpifrance", "keywords": ["BPIFRANCE", "BPI FRANCE"], "country": "FR"},
    {"name": "URSSAF / ACOSS", "keywords": ["URSSAF", "ACOSS"], "country": "FR"},
    {"name": "Assurance maladie / retraite / famille", "keywords": ["CPAM", "CARSAT", "CAF", "MSA"], "country": "FR"},
    {"name": "France Travail (ex-Pôle emploi)", "keywords": ["FRANCE TRAVAIL", "POLE EMPLOI", "POLEEMPLOI"], "country": "FR"},
    {"name": "OPCO", "keywords": ["OPCO"], "country": "FR"},
    {"name": "Collectivités territoriales", "keywords": ["MAIRIE", "CONSEIL REGIONAL", "CONSEIL DEPARTEMENTAL", "METROPOLE"], "country": "FR"},
    {"name": "Établissements de santé publics", "keywords": ["CENTRE HOSPITALIER", "CHU", "HOPITAL"], "country": "FR"},
    {"name": "Justice", "keywords": ["TRIBUNAL DE COMMERCE", "GREFFE"], "country": "FR"},
    {"name": "Régulateurs", "keywords": ["AMF", "ACPR", "CNIL"], "country": "FR"},
    {"name": "Commission européenne", "keywords": ["COMMISSION EUROPEENNE"], "country": "BE"},
    {"name": "Banque centrale européenne", "keywords": ["BCE", "BANQUE CENTRALE EUROPEENNE"], "country": "DE"},
    {"name": "ONU", "keywords": ["ONU", "NATIONS UNIES"], "country": "US"},
    {"name": "IRS (États-Unis)", "keywords": ["IRS"], "country": "US"},
    {"name": "HMRC (Royaume-Uni)", "keywords": ["HMRC"], "country": "GB"},
]
