# securite.py
# Barrières avant l'appel au LLM (repris de AgentIA_Prod/p2_securite.py) :
#   - entrée vide ou trop longue refusée
#   - détection des tentatives d'injection de prompt (comparaison sans accents ni majuscules)
# Ces barrières complètent les instructions système de l'agent et le fait qu'aucun outil n'écrit en base.
import re

from app.rag import normaliser

LONGUEUR_MAX = 1000

# Motifs comparés au texte normalisé (minuscules, sans accents)
MOTIFS_INJECTION = [
    r"\b(ignore|oublie|ignorez|oubliez)\b.{0,30}\b(instructions?|consignes?|regles?)\b",
    r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|your)\b.{0,20}\b(instructions?|rules?)\b",
    r"\b(prompt systeme|system prompt|message systeme)\b",
    r"\b(revele|affiche|montre|donne)\b.{0,30}\b(tes|vos) (instructions|consignes|regles)\b",
    r"\btu es (maintenant|desormais)\b",
    r"\b(developer mode|mode developpeur|jailbreak)\b",
]
_MOTIFS = [re.compile(motif) for motif in MOTIFS_INJECTION]


def verifier_entree(texte):
    """Renvoie (True, "ok") si la question peut partir vers le LLM, sinon (False, raison)."""
    if not texte or not texte.strip():
        return False, "question vide"
    if len(texte) > LONGUEUR_MAX:
        return False, f"question trop longue ({len(texte)} caractères, maximum {LONGUEUR_MAX})"
    texte_normalise = normaliser(texte)
    for motif in _MOTIFS:
        if motif.search(texte_normalise):
            return False, "tentative de détournement des consignes détectée"
    return True, "ok"
