# catalogue.py
# Plugin "catalogue" : les outils (@kernel_function) qui interrogent la table produits.
# Le LLM ne voit jamais la base : il choisit un outil, et c'est NOTRE code qui exécute
# des requêtes SQL préparées à l'avance (paramétrées, en lecture seule, avec LIMIT).
# Aucun outil n'écrit dans la base : une demande de modification ne peut pas aboutir.
import json
import logging
from typing import Annotated

from mysql.connector import Error as ErreurMySQL
from semantic_kernel.functions import kernel_function

from app.db import executer_requete
from app.journal import journaliser

MAX_RESULTATS = 50  # aucune requête ne renvoie plus de lignes que cela
COLONNES_PRODUIT = "id, libelle, categorie, prix, stock, fournisseur"
# Un nom de colonne ne peut pas être passé en paramètre %s : on n'accepte que cette liste blanche
REGROUPEMENTS = ("categorie", "fournisseur")

MESSAGE_ERREUR = "Erreur technique : la base de données est momentanément indisponible."


def _executer(outil, sql, parametres=()):
    """Exécute la requête et renvoie du JSON pour le LLM. Le détail des erreurs reste dans le journal."""
    try:
        lignes = executer_requete(sql, parametres)
    except ErreurMySQL as erreur:
        journaliser("erreur_bd", logging.ERROR, outil=outil, erreur=str(erreur)[:200])
        return MESSAGE_ERREUR
    if not lignes:
        return "Aucun résultat."
    return json.dumps(lignes, ensure_ascii=False)


class CataloguePlugin:

    @kernel_function(description=(
        "Recherche des produits du catalogue (id, libellé, catégorie, prix en euros HT, stock, fournisseur). "
        "Tous les filtres sont optionnels et cumulables ; sans filtre, renvoie tout le catalogue."))
    def rechercher_produits(
        self,
        mot_cle: Annotated[str | None, "Mot contenu dans le libellé, ex : switch, écran, toner"] = None,
        categorie: Annotated[str | None, "Catégorie exacte, ex : Informatique, Réseau, Mobilier"] = None,
        prix_min: Annotated[float | None, "Prix minimum en euros HT"] = None,
        prix_max: Annotated[float | None, "Prix maximum en euros HT"] = None,
    ) -> str:
        sql = f"SELECT {COLONNES_PRODUIT} FROM produits WHERE 1=1"
        parametres = []
        if mot_cle:
            sql += " AND libelle LIKE %s"
            parametres.append(f"%{mot_cle}%")
        if categorie:
            sql += " AND categorie = %s"
            parametres.append(categorie)
        if prix_min is not None:
            sql += " AND prix >= %s"
            parametres.append(prix_min)
        if prix_max is not None:
            sql += " AND prix <= %s"
            parametres.append(prix_max)
        sql += f" ORDER BY prix LIMIT {MAX_RESULTATS}"
        return _executer("rechercher_produits", sql, parametres)

    @kernel_function(description="Liste les produits d'un fournisseur (raison sociale complète ou partielle).")
    def produits_fournisseur(
        self,
        fournisseur: Annotated[str, "Raison sociale du fournisseur, ex : NetLink Systèmes"],
    ) -> str:
        sql = (f"SELECT {COLONNES_PRODUIT} FROM produits WHERE fournisseur LIKE %s "
               f"ORDER BY libelle LIMIT {MAX_RESULTATS}")
        return _executer("produits_fournisseur", sql, (f"%{fournisseur}%",))

    @kernel_function(description=(
        "Liste les produits dont le stock est inférieur ou égal à un seuil, du plus faible au plus élevé. "
        "Un stock de 0 signifie une rupture : utiliser seuil=0 pour les ruptures de stock."))
    def stock_faible(
        self,
        seuil: Annotated[int, "Seuil de stock, ex : 5 (0 pour les seules ruptures)"] = 5,
    ) -> str:
        if seuil < 0:
            return "Le seuil doit être positif ou nul."
        sql = (f"SELECT {COLONNES_PRODUIT} FROM produits WHERE stock <= %s "
               f"ORDER BY stock, libelle LIMIT {MAX_RESULTATS}")
        return _executer("stock_faible", sql, (seuil,))

    @kernel_function(description=(
        "Statistiques du stock regroupées par catégorie ou par fournisseur : nombre de produits, "
        "quantité totale en stock et valeur du stock en euros HT (somme de prix x stock)."))
    def valeur_stock(
        self,
        regroupement: Annotated[str, "categorie ou fournisseur"] = "categorie",
    ) -> str:
        if regroupement not in REGROUPEMENTS:
            return "Regroupement impossible. Valeurs possibles : " + ", ".join(REGROUPEMENTS)
        sql = (f"SELECT {regroupement}, COUNT(*) AS nb_produits, "
               f"CAST(SUM(stock) AS SIGNED) AS stock_total, "
               f"ROUND(SUM(prix * stock), 2) AS valeur_stock_euros "
               f"FROM produits GROUP BY {regroupement} ORDER BY valeur_stock_euros DESC")
        return _executer("valeur_stock", sql)

    @kernel_function(description=(
        "Liste les catégories et les fournisseurs du catalogue avec leur nombre de produits. "
        "Utile pour connaître les noms exacts avant une recherche."))
    def lister_categories_et_fournisseurs(self) -> str:
        sql = ("SELECT categorie, fournisseur, COUNT(*) AS nb_produits FROM produits "
               "GROUP BY categorie, fournisseur ORDER BY categorie")
        return _executer("lister_categories_et_fournisseurs", sql)
