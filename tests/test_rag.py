# test_rag.py
# Lecture, découpage, index en cache et recherche RAG, avec un FAUX service d'embeddings (aucun appel Azure).
import asyncio
import shutil

import pytest

from app import rag
from app.plugins.fiches import MESSAGE_ERREUR, FichesPlugin
from app.rag import IndexRag, charger_morceaux, decouper, lire_pdf
from tests.conftest import ServiceEnPanne

FOURNISSEURS = {"NovaTech Distribution", "Papyrus & Co", "ErgoMobil", "SonoriQ Audio", "NetLink Systèmes",
                "CaféoPro", "ClearHygiène Services", "VisioPrint"}


def construire(service, dossier, cache):
    return asyncio.run(IndexRag(service, dossier, cache).construire())


# ---------- Lecture et découpage ----------
def test_lecture_pdf_sans_pied_de_page(dossier_fiches):
    texte = lire_pdf(dossier_fiches / "FRN-005_NetLink_Systemes.pdf")
    assert "03 20 00 50 05" in texte
    assert "Document fictif" not in texte and "Page 1" not in texte


def test_decoupage_une_section_par_morceau(dossier_fiches):
    morceaux = charger_morceaux(dossier_fiches)
    assert len(morceaux) == 40  # 8 fiches x 5 sections
    assert {m.fournisseur for m in morceaux} == FOURNISSEURS  # mêmes raisons sociales que la base
    assert len({m.source for m in morceaux}) == 8


def test_chaque_morceau_prefixe_par_son_fournisseur(dossier_fiches):
    for m in charger_morceaux(dossier_fiches):
        assert m.texte.startswith(f"Fournisseur : {m.fournisseur} (fiche {m.source})")


def test_section_trop_longue_redecoupee_avec_chevauchement(monkeypatch):
    monkeypatch.setattr(rag, "TAILLE_MAX_MORCEAU", 100)
    monkeypatch.setattr(rag, "CHEVAUCHEMENT", 20)
    texte = "Raison sociale\nACME\n1. Identification\n" + "x" * 250
    morceaux = decouper(texte, "acme.pdf")
    assert len(morceaux) == 4 and all(m.fournisseur == "ACME" for m in morceaux)


# ---------- Index : calculé une fois, puis lu dans le cache ----------
def test_index_calcule_une_seule_fois_puis_cache(faux_service, dossier_fiches, tmp_path):
    construire(faux_service, dossier_fiches, tmp_path)
    assert faux_service.nb_appels == 1 and faux_service.nb_textes == 40

    deuxieme_service = type(faux_service)()
    index = construire(deuxieme_service, dossier_fiches, tmp_path)
    assert deuxieme_service.nb_appels == 0  # tout vient du cache
    assert len(index.morceaux) == 40 and index.vecteurs.shape == (40, 512)


def test_index_recalcule_si_une_fiche_change(faux_service, dossier_fiches, tmp_path):
    fiches = tmp_path / "fiches"
    fiches.mkdir()
    for nom in ("FRN-003_ErgoMobil.pdf", "FRN-006_CafeoPro.pdf"):
        shutil.copy(dossier_fiches / nom, fiches)
    assert len(construire(faux_service, fiches, tmp_path / "cache").morceaux) == 10

    (fiches / "FRN-006_CafeoPro.pdf").unlink()
    assert len(construire(faux_service, fiches, tmp_path / "cache").morceaux) == 5
    assert faux_service.nb_appels == 2


def test_dossier_absent(faux_service, tmp_path):
    with pytest.raises(FileNotFoundError):
        construire(faux_service, tmp_path / "inexistant", tmp_path)


# ---------- Recherche ----------
@pytest.fixture
def index(faux_service, dossier_fiches, tmp_path):
    return construire(faux_service, dossier_fiches, tmp_path)


def test_recherche_trouve_les_certifies_iso_14001(index):
    resultats = asyncio.run(index.rechercher("certifications ISO 14001", nombre=4))
    trouves = {m.fournisseur for _, m in resultats if "ISO 14001" in m.texte}
    assert trouves == {"NovaTech Distribution", "ClearHygiène Services"}


def test_recherche_triee_par_pertinence(index):
    scores = [score for score, _ in asyncio.run(index.rechercher("conditions de paiement", nombre=8))]
    assert scores == sorted(scores, reverse=True)


def test_filtre_fournisseur_sans_accent(index):
    resultats = asyncio.run(index.rechercher("telephone", fournisseur="clearhygiene", nombre=8))
    assert len(resultats) == 5 and {m.fournisseur for _, m in resultats} == {"ClearHygiène Services"}
    assert asyncio.run(index.rechercher("telephone", fournisseur="Inconnu SA")) == []


# ---------- Outil de l'agent ----------
def test_outil_cite_la_fiche_source(index):
    reponse = asyncio.run(FichesPlugin(index).rechercher_fiches("téléphone", fournisseur="NetLink Systèmes"))
    assert "[Source : FRN-005_NetLink_Systemes.pdf" in reponse
    assert "03 20 00 50 05" in reponse


def test_outil_masque_les_erreurs_techniques(index):
    index.service = ServiceEnPanne()
    reponse = asyncio.run(FichesPlugin(index).rechercher_fiches("paiement"))
    assert reponse == MESSAGE_ERREUR and "api_key" not in reponse
