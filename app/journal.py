# journal.py
# Logs structurés JSON (repris de AgentIA_Prod/p3_observabilite.py et p4_couts.py) :
#   - niveau (LOG_LEVEL) et fichier (LOG_FILE) configurables, avec rotation
#   - question tronquée, outils appelés, durée, erreurs, tokens, coût estimé
#   - aucune clé ni donnée sensible : textes tronqués et secrets masqués avant écriture
# Bilan des coûts et de l'usage à partir du journal : python -m app.journal
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TAILLE_MAX_TEXTE = 80  # on tronque les textes journalisés (RGPD, données personnelles)

# « api_key=xxx », « password: xxx », « Bearer xxx »... : la valeur est remplacée par ***
MOTIFS_SECRETS = [
    re.compile(r"(?i)\b(api[_-]?key|password|passwd|mot de passe|secret|token)(\s*[=:]\s*)[^\s,;\"']+"),
    re.compile(r"(?i)\b(bearer)(\s+)[^\s,;\"']+"),
]


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


def masquer_secrets(texte):
    """Remplace par *** les secrets de l'application et toute valeur du type « api_key=... »."""
    for nom in ("AZURE_OPENAI_API_KEY", "MYSQL_PASSWORD"):
        valeur = os.getenv(nom)
        if valeur and len(valeur) >= 6:
            texte = texte.replace(valeur, "***")
    for motif in MOTIFS_SECRETS:
        texte = motif.sub(r"\1\2***", texte)
    return texte


def estimer_cout(tokens_entree, tokens_sortie):
    """Coût estimé en euros, à partir des prix pour 1 million de tokens définis dans .env."""
    prix_entree = float(os.getenv("PRIX_ENTREE_1M_TOKENS", "1.00"))
    prix_sortie = float(os.getenv("PRIX_SORTIE_1M_TOKENS", "4.00"))
    return round((tokens_entree * prix_entree + tokens_sortie * prix_sortie) / 1_000_000, 6)


def journaliser(evenement, niveau=logging.INFO, **donnees):
    """Écrit un événement JSON : journaliser("appel_outil", outil="stock_faible", duree_ms=12)."""
    horodatage = datetime.now().isoformat(timespec="seconds")
    ligne = json.dumps({"horodatage": horodatage, "niveau": logging.getLevelName(niveau),
                        "evenement": evenement, **donnees}, ensure_ascii=False, default=str)
    log.log(niveau, masquer_secrets(ligne))


# ---------- Bilan à partir du journal ----------
def bilan(fichier=None):
    """Additionne questions, erreurs, tokens, coût et durées de tous les fichiers du journal (rotation incluse)."""
    fichier = Path(fichier or os.getenv("LOG_FILE", "logs/assistant.jsonl"))
    resultat = {"questions": 0, "refusees": 0, "erreurs": 0, "tokens_entree": 0, "tokens_sortie": 0,
                "cout_euros": 0.0, "durees_ms": [], "outils": Counter()}
    for chemin in sorted(fichier.parent.glob(fichier.name + "*")):
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            try:
                evenement = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            nom = evenement.get("evenement")
            if nom == "question":
                resultat["questions"] += 1
                resultat["tokens_entree"] += evenement.get("tokens_entree", 0)
                resultat["tokens_sortie"] += evenement.get("tokens_sortie", 0)
                resultat["cout_euros"] += evenement.get("cout_euros", 0.0)
                resultat["durees_ms"].append(evenement.get("duree_ms", 0))
                resultat["outils"].update(evenement.get("outils", []))
            elif nom == "question_refusee":
                resultat["refusees"] += 1
            elif evenement.get("niveau") == "ERROR":
                resultat["erreurs"] += 1
    return resultat


if __name__ == "__main__":
    b = bilan()
    durees = b["durees_ms"] or [0]
    print("===== Bilan du journal =====")
    print(f"Questions traitées : {b['questions']}  (refusées : {b['refusees']}, erreurs : {b['erreurs']})")
    print(f"Tokens             : {b['tokens_entree']} en entrée + {b['tokens_sortie']} en sortie")
    print(f"Coût estimé        : {b['cout_euros']:.4f} €  (soit {b['cout_euros'] / max(b['questions'], 1):.5f} € par question)")
    print(f"Durée              : moyenne {sum(durees) / len(durees):.0f} ms, maximum {max(durees)} ms")
    print("Outils les plus appelés :", ", ".join(f"{nom} ({n})" for nom, n in b["outils"].most_common(5)) or "aucun")
