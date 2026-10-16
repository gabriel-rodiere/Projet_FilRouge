# fiches.py
# Plugin "fiches" : la recherche sémantique dans les fiches PDF fournisseurs, exposée comme outil de l'agent.
#   - rechercher_fiches(question, fournisseur) -> extraits les plus proches + fiche source citée
import logging
from typing import Annotated

from semantic_kernel.functions import kernel_function

from app.journal import journaliser

NOMBRE_MIN = 3  # extraits courts (< 600 caractères) : 3 au minimum pour ne pas rater l'information
NOMBRE_MAX = 8
MESSAGE_ERREUR = "Erreur technique : la recherche dans les fiches est momentanément indisponible."


class FichesPlugin:

    def __init__(self, index):
        self.index = index  # IndexRag déjà construit (calculé une seule fois, partagé)

    @kernel_function(description=(
        "Recherche sémantique dans les fiches PDF des fournisseurs : coordonnées (adresse, téléphone, e-mail, "
        "contact), conditions commerciales (délais, conditions de paiement, tarifs), certifications, garanties, "
        "engagements RSE, note de satisfaction et remarques du service Achats. "
        "Renvoie les extraits les plus pertinents avec la fiche source à citer."))
    async def rechercher_fiches(
        self,
        question: Annotated[str, "Ce que l'on cherche, ex : conditions de paiement, certification ISO 14001"],
        fournisseur: Annotated[str | None, "Raison sociale pour limiter la recherche à un fournisseur, ex : ErgoMobil"] = None,
        nombre: Annotated[int, "Nombre d'extraits à renvoyer (3 à 8)"] = 5,
    ) -> str:
        nombre = max(NOMBRE_MIN, min(nombre, NOMBRE_MAX))
        try:
            resultats = await self.index.rechercher(question, nombre=nombre, fournisseur=fournisseur)
        except Exception as erreur:  # service d'embeddings indisponible... : le détail reste dans le journal
            journaliser("erreur_rag", logging.ERROR, erreur=f"{type(erreur).__name__}: {str(erreur)[:200]}")
            return MESSAGE_ERREUR
        if not resultats:
            return f"Aucune fiche trouvée pour le fournisseur « {fournisseur} »." if fournisseur else "Aucun extrait trouvé."
        return "\n\n".join(f"[Source : {m.source} - {m.section} - pertinence {score:.2f}]\n{m.texte}"
                           for score, m in resultats)
