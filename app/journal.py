# journal.py
# Logs structurés JSON (repris de AgentIA_Prod/p3_observabilite.py et p4_couts.py) :
#   - niveau (LOG_LEVEL) et fichier (LOG_FILE) configurables, avec rotation
#   - question tronquée, outils appelés, durée, erreurs, tokens, coût estimé
#   - aucune clé ni donnée sensible
import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TAILLE_MAX_TEXTE = 80  # on tronque les textes journalisés (RGPD, données personnelles)


def _configurer():
    log = logging.getLogger("assistant")
    if log.handlers:  # déjà configuré (imports multiples, rechargement Streamlit)
        return log
    log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    log.propagate = False

    fichier = Path(os.getenv("LOG_FILE", "logs/assistant.jsonl"))
    fichier.parent.mkdir(parents=True, exist_ok=True)
    rotation = RotatingFileHandler(fichier, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    rotation.setFormatter(logging.Formatter("%(message)s"))  # une ligne JSON par événement
    log.addHandler(rotation)
    return log


log = _configurer()


def tronquer(texte):
    texte = str(texte)
    return texte if len(texte) <= TAILLE_MAX_TEXTE else texte[:TAILLE_MAX_TEXTE] + "..."


def journaliser(evenement, niveau=logging.INFO, **donnees):
    """Écrit un événement JSON : journaliser("appel_outil", outil="stock_faible", duree_ms=12)."""
    horodatage = datetime.now().isoformat(timespec="seconds")
    log.log(niveau, json.dumps({"horodatage": horodatage, "niveau": logging.getLevelName(niveau),
                                "evenement": evenement, **donnees}, ensure_ascii=False, default=str))
