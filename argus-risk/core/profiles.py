"""Profils de correspondance des colonnes, mémorisés par client / format de fichier.

Équivalent fichier de la table SQL `client_file_mappings` (client_id, file_format_name,
canonical_field, user_header_name). Stockage : config/mapping_profiles.json (dossier des journaux).
"""

import json
from datetime import datetime
from pathlib import Path

from . import settings as _settings



def _path() -> Path:
    return _settings.data_dir() / "mapping_profiles.json"


def load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_profile(name: str, mapping: dict) -> None:
    """Enregistre (ou remplace) le profil `name` : {champ canonique: en-tête du fichier}."""
    profiles = load()
    _path().parent.mkdir(parents=True, exist_ok=True)
    profiles[name.strip()] = {"mapping": mapping, "saved_at": datetime.now().isoformat(timespec="seconds")}
    _path().write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_profile(name: str) -> None:
    profiles = load()
    if profiles.pop(name, None) is not None:
        _path().write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
