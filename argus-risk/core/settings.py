"""Paramétrage administrable : seuils, typologies, listes de référence, liste blanche.

Principes de gouvernance (bonnes pratiques de calibrage des dispositifs de surveillance) :
- toute modification passe par un brouillon, une validation technique et une publication ;
- chaque publication est versionnée, justifiée (motif obligatoire) et tracée (avant/après, auteur, date) ;
- une version antérieure peut être restaurée ;
- l'impact d'une modification peut être mesuré sur un jeu de données avant publication
  (tests « above-the-line / below-the-line »).

Le fichier actif est `config_rules.json` (racine du projet) ; s'il n'existe pas, les valeurs par défaut du code s'appliquent.
Sur Streamlit Cloud le disque est éphémère : exporter la configuration publiée et la versionner dans Git.
"""

import copy
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import config as cfg
from . import reference_lists as ref
from .typologies import DETECTOR_REQUIRES, FAMILIES, TYPOLOGIES, Typology

CODE_PATTERN = re.compile(r"^[A-Z]{3}-\d{2,3}$")


RULES_FILE = "config_rules.json"


def config_dir() -> Path:
    """Dossier des fichiers de configuration (racine du projet par défaut ; ARGUS_CONFIG_DIR pour surcharger)."""
    return Path(os.environ.get("ARGUS_CONFIG_DIR") or Path(__file__).resolve().parent.parent)


def data_dir() -> Path:
    """Sous-dossier des journaux (historique des versions, audit, exécutions)."""
    return config_dir() / "config"


# ---------------------------------------------------------------------------
# Configuration par défaut et chargement
# ---------------------------------------------------------------------------
def _jsonable(value):
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def default_config() -> dict:
    return {
        "version": 0, "updated_at": None, "updated_by": None, "reason": "Configuration par défaut",
        "thresholds": {"n1": cfg.THRESHOLD_N1, "n2": cfg.THRESHOLD_N2, "cap": cfg.SCORE_CAP,
                       "diversity_bonus": cfg.CLIENT_DIVERSITY_BONUS},
        "exclusions": list(cfg.EXCLUSIONS),
        "lists": {
            "high_risk": dict(ref.HIGH_RISK_COUNTRIES), "tax_havens": dict(ref.TAX_HAVENS),
            "sepa": sorted(ref.SEPA_COUNTRIES), "kyc_failed": sorted(ref.KYC_FAILED),
            "reviewed": ref.REFERENCE_LISTS_REVIEWED,
        },
        "typologies": {t.code: {"enabled": True, "weight": t.weight, "name": t.name, "signal": t.signal,
                                "params": _jsonable(t.params)} for t in TYPOLOGIES},
        "custom_typologies": [],
        "whitelist": [],
        # --- Évolution 2.1 : fenêtre courte, liste blanche par libellé/contrepartie, entités publiques, devises
        "window_n": cfg.WINDOW_N,
        "whitelist_rules": {"mode": "OR", "labels": list(ref.DEFAULT_WHITELIST_LABELS),
                            "counterparties": [], "ibans": []},
        "public_entities": copy.deepcopy(ref.DEFAULT_PUBLIC_ENTITIES),
        "fx_rates": {},
        # --- Évolution 2.2 : import flexible, contexte KYC, auto-enrichissement
        "header_synonyms": {},                       # {"MONTANT": ["Montant_TTC", ...]} : synonymes ajoutés au dictionnaire
        "context": {"bonus_high": 10, "bonus_critical": 20, "kyc_volume_factor": 2.0},
        "learning": {"enabled": True},
    }


def _merge(default: dict, saved: dict) -> dict:
    out = copy.deepcopy(default)
    for key in ("version", "updated_at", "updated_by", "reason"):
        if key in saved:
            out[key] = saved[key]
    out["thresholds"].update(saved.get("thresholds", {}))
    if "exclusions" in saved:
        out["exclusions"] = saved["exclusions"]
    out["lists"].update(saved.get("lists", {}))
    for code, override in saved.get("typologies", {}).items():
        if code in out["typologies"]:
            target = out["typologies"][code]
            target.update({k: v for k, v in override.items() if k != "params"})
            target["params"].update(override.get("params", {}))
    out["custom_typologies"] = saved.get("custom_typologies", [])
    out["whitelist"] = saved.get("whitelist", [])
    if "window_n" in saved:
        out["window_n"] = saved["window_n"]
    out["whitelist_rules"].update(saved.get("whitelist_rules", {}))
    if "public_entities" in saved:
        out["public_entities"] = saved["public_entities"]
    if "fx_rates" in saved:
        out["fx_rates"] = saved["fx_rates"]
    if "header_synonyms" in saved:
        out["header_synonyms"] = saved["header_synonyms"]
    out["context"].update(saved.get("context", {}))
    out["learning"].update(saved.get("learning", {}))
    return out


def load_config() -> dict:
    path = config_dir() / RULES_FILE
    legacy = data_dir() / "rules.json"          # ancien emplacement (versions < 2.2)
    base = default_config()
    if not path.exists() and legacy.exists():
        path = legacy
    if not path.exists():
        return base
    try:
        return _merge(base, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return base


# ---------------------------------------------------------------------------
# Paramètres effectifs utilisés par le moteur
# ---------------------------------------------------------------------------
@dataclass
class Settings:
    config: dict
    all_typologies: tuple = field(default_factory=tuple)
    typologies: tuple = field(default_factory=tuple)      # typologies actives uniquement
    high_risk: dict = field(default_factory=dict)
    tax_havens: dict = field(default_factory=dict)
    sepa: set = field(default_factory=set)
    kyc_failed: set = field(default_factory=set)
    exclusions: list = field(default_factory=list)
    whitelist_ids: set = field(default_factory=set)
    window_n: int = 5
    whitelist_rules: dict = field(default_factory=dict)
    public_entities: list = field(default_factory=list)
    fx_rates: dict = field(default_factory=dict)
    header_synonyms: dict = field(default_factory=dict)
    context_cfg: dict = field(default_factory=dict)
    learning_enabled: bool = True

    @property
    def n1(self) -> int:
        return int(self.config["thresholds"]["n1"])

    @property
    def n2(self) -> int:
        return int(self.config["thresholds"]["n2"])

    @property
    def cap(self) -> int:
        return int(self.config["thresholds"]["cap"])

    @property
    def diversity_bonus(self) -> int:
        return int(self.config["thresholds"]["diversity_bonus"])

    @property
    def version(self) -> int:
        return int(self.config.get("version", 0))

    def level_for(self, score) -> str:
        if score >= self.n2:
            return cfg.LEVEL_N2
        if score >= self.n1:
            return cfg.LEVEL_N1
        return cfg.LEVEL_LOW


def build_settings(config: dict) -> Settings:
    builtin = {t.code: t for t in TYPOLOGIES}
    everything, active = [], []
    for code, t in builtin.items():
        ov = config["typologies"].get(code, {})
        typo = Typology(code, ov.get("name", t.name), int(ov.get("weight", t.weight)),
                        ov.get("signal", t.signal), t.detector, dict(ov.get("params", t.params)))
        everything.append(typo)
        if ov.get("enabled", True):
            active.append(typo)
    for c in config.get("custom_typologies", []):
        typo = Typology(c["code"], c["name"], int(c["weight"]), c.get("signal", ""), c["detector"],
                        dict(c.get("params", {})))
        everything.append(typo)
        if c.get("enabled", True):
            active.append(typo)
    lists = config["lists"]
    return Settings(
        config=config, all_typologies=tuple(everything), typologies=tuple(active),
        high_risk={k.upper(): v for k, v in lists["high_risk"].items()},
        tax_havens={k.upper(): v for k, v in lists["tax_havens"].items()},
        sepa={c.upper() for c in lists["sepa"]},
        kyc_failed={ref.clean_token(x) for x in lists["kyc_failed"]},
        exclusions=[ref.clean_token(x) for x in config["exclusions"] if ref.clean_token(x)],
        whitelist_ids={str(w["id"]).strip() for w in config.get("whitelist", []) if str(w.get("id", "")).strip()},
        window_n=int(config.get("window_n", cfg.WINDOW_N) or 0),
        whitelist_rules=dict(config.get("whitelist_rules", {})),
        public_entities=list(config.get("public_entities", [])),
        fx_rates={str(k).upper(): float(v) for k, v in config.get("fx_rates", {}).items()},
        header_synonyms={str(k).upper(): [str(x) for x in v] for k, v in config.get("header_synonyms", {}).items()},
        context_cfg=dict(config.get("context", {})),
        learning_enabled=bool(config.get("learning", {}).get("enabled", True)),
    )


_CACHE = {}


def load_settings() -> Settings:
    """Paramètres effectifs, mis en cache tant que config_rules.json n'a pas changé (évite de tout reconstruire à chaque rafraîchissement de page)."""
    path = config_dir() / RULES_FILE
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
    except OSError:
        stamp = (str(path), None)
    if _CACHE.get("stamp") != stamp:
        _CACHE["stamp"], _CACHE["settings"] = stamp, build_settings(load_config())
    return _CACHE["settings"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_config(config: dict) -> list:
    """Retourne la liste des erreurs de configuration (liste vide = valide)."""
    errors = []
    t = config["thresholds"]
    try:
        n1, n2, cap, bonus = int(t["n1"]), int(t["n2"]), int(t["cap"]), int(t["diversity_bonus"])
        if not 0 < n1 < n2 <= cap <= 1000:
            errors.append("Seuils incohérents : il faut 0 < N1 < N2 ≤ plafond (≤ 1000).")
        if not 0 <= bonus <= 50:
            errors.append("Le bonus de diversité doit être compris entre 0 et 50.")
    except (TypeError, ValueError, KeyError):
        errors.append("Seuils illisibles (entiers attendus).")
    for code, ov in config["typologies"].items():
        if not 0 <= int(ov.get("weight", 0)) <= 100:
            errors.append(f"{code} : le poids doit être compris entre 0 et 100.")
    seen = set(config["typologies"])
    for c in config.get("custom_typologies", []):
        code = str(c.get("code", ""))
        if not CODE_PATTERN.match(code) or code.split("-")[0] not in FAMILIES:
            errors.append(f"{code or '(vide)'} : code invalide (format AAA-01, préfixe parmi {', '.join(FAMILIES)}).")
        if code in seen:
            errors.append(f"{code} : code déjà utilisé.")
        seen.add(code)
        if c.get("detector") not in DETECTOR_REQUIRES:
            errors.append(f"{code} : détecteur inconnu « {c.get('detector')} ».")
        if not str(c.get("name", "")).strip():
            errors.append(f"{code} : nom obligatoire.")
        if not isinstance(c.get("params", {}), dict):
            errors.append(f"{code} : les paramètres doivent être un objet JSON.")
        if not 0 <= int(c.get("weight", 0)) <= 100:
            errors.append(f"{code} : le poids doit être compris entre 0 et 100.")
    try:
        if not 0 <= int(config.get("window_n", 0)) <= 100:
            errors.append("La fenêtre N doit être comprise entre 0 (désactivée) et 100 transactions.")
    except (TypeError, ValueError):
        errors.append("La fenêtre N doit être un entier.")
    wr = config.get("whitelist_rules", {})
    if str(wr.get("mode", "OR")).upper() not in ("OR", "AND"):
        errors.append("Liste blanche : le mode doit être OR ou AND.")
    for entity in config.get("public_entities", []):
        if not str(entity.get("name", "")).strip() or not entity.get("keywords"):
            errors.append(f"Entité publique « {entity.get('name') or '(sans nom)'} » : nom et mots-clés obligatoires.")
        if not re.fullmatch(r"[A-Za-z]{2}", str(entity.get("country", ""))):
            errors.append(f"Entité publique « {entity.get('name')} » : pays attendu au format ISO2.")
    ctx_cfg = config.get("context", {})
    try:
        if not (0 <= int(ctx_cfg.get("bonus_high", 0)) <= 50 and 0 <= int(ctx_cfg.get("bonus_critical", 0)) <= 50):
            errors.append("Les bonus de contexte doivent être compris entre 0 et 50 points.")
        if float(ctx_cfg.get("kyc_volume_factor", 2)) <= 0:
            errors.append("Le facteur d'écart au volume KYC doit être positif.")
    except (TypeError, ValueError):
        errors.append("Paramètres de contexte illisibles.")
    for cur, rate in config.get("fx_rates", {}).items():
        try:
            if float(rate) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Taux de change {cur} : nombre positif attendu.")
    for name in ("high_risk", "tax_havens"):
        for code in config["lists"][name]:
            if not re.fullmatch(r"[A-Za-z]{2}", str(code)):
                errors.append(f"Liste {name} : « {code} » n'est pas un code pays ISO2.")
    return errors


def dry_run(config: dict) -> list:
    """Exécute le moteur sur les données de démonstration avec cette configuration ; retourne les erreurs."""
    from .data import normalize
    from .engine import run_analysis
    from .sample import demo_dataframe
    try:
        settings = build_settings(config)
        frame, _ = normalize(demo_dataframe(), settings.exclusions)
        result = run_analysis(frame, settings)
    except Exception as exc:  # noqa: BLE001
        return [f"Exécution impossible : {type(exc).__name__}: {exc}"]
    broken = result.typology_status[result.typology_status["Statut"] == "Erreur"]
    return [f"{r['Code']} : {r['Colonnes manquantes']}" for _, r in broken.iterrows()]


# ---------------------------------------------------------------------------
# Comparaison, publication, historique
# ---------------------------------------------------------------------------
def diff_configs(old: dict, new: dict) -> list:
    """Liste lisible des modifications entre deux configurations."""
    changes = []

    def add(section, item, before, after):
        changes.append({"Section": section, "Élément": item, "Avant": str(before), "Après": str(after)})

    for key, label in (("n1", "Seuil N1"), ("n2", "Seuil N2"), ("cap", "Plafond du score"),
                       ("diversity_bonus", "Bonus de diversité client")):
        if old["thresholds"].get(key) != new["thresholds"].get(key):
            add("Scores & seuils", label, old["thresholds"].get(key), new["thresholds"].get(key))
    if old["exclusions"] != new["exclusions"]:
        add("Scores & seuils", "Mots exclus", ", ".join(old["exclusions"]), ", ".join(new["exclusions"]))
    for name, label in (("high_risk", "Pays à haut risque"), ("tax_havens", "Territoires fiscaux"),
                        ("sepa", "Zone SEPA"), ("kyc_failed", "Statuts KYC défaillants")):
        a, b = old["lists"][name], new["lists"][name]
        ka, kb = (set(a), set(b)) if isinstance(a, dict) else (set(a), set(b))
        if ka != kb:
            add("Listes de référence", label,
                f"retirés : {', '.join(sorted(ka - kb)) or '—'}", f"ajoutés : {', '.join(sorted(kb - ka)) or '—'}")
    if old["lists"].get("reviewed") != new["lists"].get("reviewed"):
        add("Listes de référence", "Dernière validation", old["lists"].get("reviewed"), new["lists"].get("reviewed"))
    for code, nt in new["typologies"].items():
        ot = old["typologies"].get(code)
        if not ot:
            continue
        for key, label in (("enabled", "activée"), ("weight", "poids"), ("name", "nom"), ("signal", "signal")):
            if ot.get(key) != nt.get(key):
                add("Typologies", f"{code} — {label}", ot.get(key), nt.get(key))
        for pk in sorted(set(ot["params"]) | set(nt["params"])):
            if ot["params"].get(pk) != nt["params"].get(pk):
                add("Typologies", f"{code} — paramètre {pk}", ot["params"].get(pk), nt["params"].get(pk))
    oc = {c["code"]: c for c in old.get("custom_typologies", [])}
    nc = {c["code"]: c for c in new.get("custom_typologies", [])}
    for code in sorted(set(nc) - set(oc)):
        add("Typologies personnalisées", code, "—", f"créée : {nc[code]['name']}")
    for code in sorted(set(oc) - set(nc)):
        add("Typologies personnalisées", code, oc[code]["name"], "supprimée")
    for code in sorted(set(oc) & set(nc)):
        if oc[code] != nc[code]:
            add("Typologies personnalisées", code, "version précédente", "modifiée")
    if old.get("window_n") != new.get("window_n"):
        add("Scores & seuils", "Fenêtre N (dernières transactions)", old.get("window_n"), new.get("window_n"))
    ow_rules, nw_rules = old.get("whitelist_rules", {}), new.get("whitelist_rules", {})
    for key, label in (("mode", "mode"), ("labels", "libellés de confiance"),
                       ("counterparties", "contreparties de confiance"), ("ibans", "IBAN de confiance")):
        if ow_rules.get(key) != nw_rules.get(key):
            add("Liste blanche (règles)", label, ow_rules.get(key), nw_rules.get(key))
    old_pe = {e["name"]: e for e in old.get("public_entities", [])}
    new_pe = {e["name"]: e for e in new.get("public_entities", [])}
    if old_pe != new_pe:
        add("Entités publiques", "Référentiel",
            f"retirées : {', '.join(sorted(set(old_pe) - set(new_pe))) or '—'}",
            f"ajoutées : {', '.join(sorted(set(new_pe) - set(old_pe))) or '—'} ; "
            f"modifiées : {', '.join(sorted(n for n in set(old_pe) & set(new_pe) if old_pe[n] != new_pe[n])) or '—'}")
    if old.get("header_synonyms") != new.get("header_synonyms"):
        add("Import", "Synonymes d'en-têtes", old.get("header_synonyms"), new.get("header_synonyms"))
    if old.get("context") != new.get("context"):
        add("Contexte & KYC", "Paramètres de contexte", old.get("context"), new.get("context"))
    if old.get("learning") != new.get("learning"):
        add("Auto-enrichissement", "Apprentissage", old.get("learning"), new.get("learning"))
    if old.get("fx_rates") != new.get("fx_rates"):
        add("Devises", "Taux de change", old.get("fx_rates"), new.get("fx_rates"))
    ow = {w["id"] for w in old.get("whitelist", [])}
    nw = {w["id"] for w in new.get("whitelist", [])}
    if ow != nw:
        add("Liste blanche", "Clients exemptés", f"retirés : {', '.join(sorted(ow - nw)) or '—'}",
            f"ajoutés : {', '.join(sorted(nw - ow)) or '—'}")
    return changes


def _append(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def publish(draft: dict, author: str, reason: str) -> dict:
    """Valide, versionne, enregistre et trace une nouvelle configuration. Lève ValueError si refus."""
    if not author.strip() or not reason.strip():
        raise ValueError("L'auteur et le motif de la modification sont obligatoires.")
    errors = validate_config(draft) or dry_run(draft)
    if errors:
        raise ValueError("Configuration refusée : " + " ; ".join(errors))
    current = load_config()
    changes = diff_configs(current, draft)
    new = copy.deepcopy(draft)
    new.update({"version": int(current.get("version", 0)) + 1,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "updated_by": author.strip(), "reason": reason.strip()})
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / (RULES_FILE + ".tmp")
    temp.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(directory / RULES_FILE)
    directory = data_dir()
    _append(directory / "history.jsonl", {"version": new["version"], "at": new["updated_at"],
                                          "by": new["updated_by"], "reason": new["reason"], "config": new})
    _append(directory / "audit_log.jsonl", {"version": new["version"], "at": new["updated_at"],
                                            "by": new["updated_by"], "reason": new["reason"], "changes": changes})
    return new


def read_history() -> list:
    return _read_jsonl(data_dir() / "history.jsonl")


def read_audit() -> list:
    return _read_jsonl(data_dir() / "audit_log.jsonl")


# ---------------------------------------------------------------------------
# Accès administrateur
# ---------------------------------------------------------------------------
def admin_password() -> str:
    """Mot de passe administrateur : variable ARGUS_ADMIN_PASSWORD ou secret Streamlit ADMIN_PASSWORD."""
    value = os.environ.get("ARGUS_ADMIN_PASSWORD", "")
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get("ADMIN_PASSWORD", ""))
    except Exception:  # noqa: BLE001  (aucun secret configuré)
        return ""


def check_admin_password(candidate: str) -> bool:
    expected = admin_password()
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())
