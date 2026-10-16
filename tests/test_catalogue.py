# test_catalogue.py
# Les outils du plugin "catalogue", exécutés sur la base de test (scripts sql/00, 01, 02).
import json

import pytest
from mysql.connector import Error as ErreurMySQL

from app.plugins import catalogue
from app.plugins.catalogue import CataloguePlugin

plugin = CataloguePlugin()


# ---------- Avec la base ----------
@pytest.mark.bd
def test_ruptures_de_stock(base_disponible):
    produits = json.loads(plugin.stock_faible(seuil=0))
    assert {p["id"] for p in produits} == {4, 15, 28, 38}
    assert all(p["stock"] == 0 for p in produits)


@pytest.mark.bd
def test_informatique_moins_de_200_euros_tries_par_prix(base_disponible):
    produits = json.loads(plugin.rechercher_produits(categorie="Informatique", prix_max=200))
    assert [p["id"] for p in produits] == [6, 5, 3]  # souris 29,90 / station 129 / écran 159,90


@pytest.mark.bd
def test_recherche_insensible_aux_accents_et_a_la_casse(base_disponible):
    assert len(json.loads(plugin.produits_fournisseur("cafeopro"))) == 4
    assert "Écran" in plugin.rechercher_produits(mot_cle="ecran")


@pytest.mark.bd
def test_valeur_du_stock_par_fournisseur(base_disponible):
    lignes = json.loads(plugin.valeur_stock("fournisseur"))
    assert len(lignes) == 8
    assert lignes[0] == {"fournisseur": "NovaTech Distribution", "nb_produits": 6,
                         "stock_total": 189, "valeur_stock_euros": 27290.5}
    assert sum(ligne["nb_produits"] for ligne in lignes) == 38


@pytest.mark.bd
def test_resultats_limites_par_LIMIT(base_disponible, monkeypatch):
    monkeypatch.setattr(catalogue, "MAX_RESULTATS", 3)
    assert len(json.loads(plugin.rechercher_produits())) == 3


@pytest.mark.bd
def test_aucun_resultat(base_disponible):
    assert plugin.rechercher_produits(mot_cle="produit-inexistant-xyz") == "Aucun résultat."


# ---------- Sans la base : contrôles faits AVANT toute requête ----------
def _interdire_requete(monkeypatch):
    def requete_interdite(*args, **kwargs):
        raise AssertionError("aucune requête ne doit partir vers la base")
    monkeypatch.setattr(catalogue, "executer_requete", requete_interdite)


def test_regroupement_hors_liste_blanche_refuse(monkeypatch):
    _interdire_requete(monkeypatch)
    resultat = plugin.valeur_stock("prix; DROP TABLE produits")
    assert resultat.startswith("Regroupement impossible")


def test_seuil_negatif_refuse(monkeypatch):
    _interdire_requete(monkeypatch)
    assert plugin.stock_faible(-1) == "Le seuil doit être positif ou nul."


def test_parametres_passes_a_part_du_sql(monkeypatch):
    """Requête paramétrée : la saisie ne se retrouve jamais dans le texte SQL."""
    appels = []
    monkeypatch.setattr(catalogue, "executer_requete", lambda sql, parametres=(): appels.append((sql, parametres)) or [])
    plugin.rechercher_produits(mot_cle="x' OR '1'='1")
    sql, parametres = appels[0]
    assert "OR '1'='1" not in sql and "%s" in sql
    assert parametres == ["%x' OR '1'='1%"]


def test_erreur_de_base_masquee(monkeypatch):
    def base_en_panne(*args, **kwargs):
        raise ErreurMySQL(msg="Access denied for user 'agent_ia'@'10.0.0.1' (using password: YES)")
    monkeypatch.setattr(catalogue, "executer_requete", base_en_panne)
    resultat = plugin.stock_faible(0)
    assert resultat == catalogue.MESSAGE_ERREUR
    assert "agent_ia" not in resultat and "password" not in resultat
