# rag.py
# RAG sur les fiches fournisseurs :
#   1. lire tous les PDF du dossier FICHES_DIR (pypdf)
#   2. découper par section, chaque morceau préfixé par la raison sociale du fournisseur
#   3. calculer les embeddings UNE SEULE FOIS (cache dans RAG_CACHE_DIR)
#   4. rechercher les morceaux les plus proches d'une question (similarité cosinus)
# Le service d'embeddings est passé en paramètre : les tests utilisent un faux service, sans Azure.
# Test de la recherche seule : python -m app.rag "certifications ISO 14001"
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from pypdf import PdfReader

from app.journal import journaliser

load_dotenv()

VERSION_DECOUPAGE = "2"   # à incrémenter si le découpage change : le cache est alors recalculé
TAILLE_MAX_MORCEAU = 1200  # caractères ; au-delà, une section est redécoupée
CHEVAUCHEMENT = 150        # caractères repris d'un morceau au suivant (redécoupage uniquement)

# Lignes de pied de page sans intérêt pour la recherche
LIGNES_IGNOREES = re.compile(r"^(Document fictif.*|Page \d+)$")
# Titre de section : « 1. Identification », « 4. Évaluation interne du service Achats »...
TITRE_SECTION = re.compile(r"^(\d+)\.\s+(.+)$")


@dataclass
class Morceau:
    source: str        # nom du fichier PDF, cité dans les réponses
    fournisseur: str   # raison sociale
    section: str
    texte: str         # texte indexé, préfixé par le fournisseur et la section


def normaliser(texte):
    """Minuscules sans accents : « ClearHygiène » et « clearhygiene » deviennent identiques."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return sans_accents.lower().strip()


# ---------- 1. Lecture des PDF ----------
def lire_pdf(chemin):
    lecteur = PdfReader(chemin)
    lignes = []
    for page in lecteur.pages:
        for ligne in (page.extract_text() or "").splitlines():
            ligne = ligne.strip()
            if ligne and not LIGNES_IGNOREES.match(ligne):
                lignes.append(ligne)
    return "\n".join(lignes)


def raison_sociale(texte, nom_fichier):
    """La ligne qui suit « Raison sociale », sinon celle qui suit « FICHE FOURNISSEUR », sinon le nom du fichier."""
    lignes = texte.splitlines()
    for repere in ("Raison sociale", "FICHE FOURNISSEUR"):
        if repere in lignes:
            i = lignes.index(repere)
            if i + 1 < len(lignes):
                return lignes[i + 1]
    return Path(nom_fichier).stem


# ---------- 2. Découpage ----------
def _redecouper(texte):
    """Découpe un texte trop long en morceaux de TAILLE_MAX_MORCEAU avec chevauchement."""
    if len(texte) <= TAILLE_MAX_MORCEAU:
        return [texte]
    pas = TAILLE_MAX_MORCEAU - CHEVAUCHEMENT
    return [texte[i:i + TAILLE_MAX_MORCEAU] for i in range(0, len(texte), pas)]


def decouper(texte, source):
    """Une fiche -> un morceau par section numérotée, chacun préfixé par la raison sociale."""
    fournisseur = raison_sociale(texte, source)
    sections = []  # (titre, lignes)
    titre, contenu = "En-tête", []
    for ligne in texte.splitlines():
        trouve = TITRE_SECTION.match(ligne)
        if trouve:
            if contenu:
                sections.append((titre, contenu))
            titre, contenu = trouve.group(2), []
        else:
            contenu.append(ligne)
    if contenu:
        sections.append((titre, contenu))

    morceaux = []
    for titre, contenu in sections:
        if titre == "En-tête":  # titre de la fiche et référence : déjà dans le préfixe
            continue
        for partie in _redecouper("\n".join(contenu)):
            entete = f"Fournisseur : {fournisseur} (fiche {source})\nSection : {titre}\n"
            morceaux.append(Morceau(source, fournisseur, titre, entete + partie))
    return morceaux


def charger_morceaux(dossier):
    morceaux = []
    for chemin in sorted(Path(dossier).glob("*.pdf")):
        morceaux += decouper(lire_pdf(chemin), chemin.name)
    return morceaux


# ---------- 3 et 4. L'index : embeddings calculés une fois, puis recherche ----------
class IndexRag:

    def __init__(self, service_embeddings, dossier=None, dossier_cache=None):
        self.service = service_embeddings  # tout objet avec : async generate_embeddings(list[str]) -> ndarray
        self.dossier = Path(dossier or os.getenv("FICHES_DIR", "fiches_fournisseurs"))
        self.dossier_cache = Path(dossier_cache or os.getenv("RAG_CACHE_DIR", "cache"))
        self.morceaux: list[Morceau] = []
        self.vecteurs = None  # matrice (nb_morceaux, dimension), lignes normalisées

    def _signature(self):
        """Empreinte des PDF + modèle + version du découpage : elle change si l'un d'eux change."""
        empreinte = hashlib.sha256(f"{VERSION_DECOUPAGE}|{getattr(self.service, 'ai_model_id', '')}".encode())
        for chemin in sorted(self.dossier.glob("*.pdf")):
            empreinte.update(chemin.name.encode())
            empreinte.update(chemin.read_bytes())
        return empreinte.hexdigest()[:16]

    async def construire(self):
        """Charge l'index depuis le cache, ou le calcule (une seule fois) puis le met en cache."""
        if not self.dossier.is_dir():
            raise FileNotFoundError(f"Dossier des fiches introuvable : {self.dossier}")
        signature = self._signature()
        fichier_vecteurs = self.dossier_cache / f"index_{signature}.npy"
        fichier_morceaux = self.dossier_cache / f"index_{signature}.json"

        if fichier_vecteurs.exists() and fichier_morceaux.exists():
            self.morceaux = [Morceau(**m) for m in json.loads(fichier_morceaux.read_text(encoding="utf-8"))]
            self.vecteurs = np.load(fichier_vecteurs, allow_pickle=False)
            journaliser("index_rag_cache", morceaux=len(self.morceaux))
            return self

        debut = time.perf_counter()
        self.morceaux = charger_morceaux(self.dossier)
        if not self.morceaux:
            raise ValueError(f"Aucune fiche PDF exploitable dans {self.dossier}")
        vecteurs = await self.service.generate_embeddings([m.texte for m in self.morceaux])
        self.vecteurs = self._normaliser(np.asarray(vecteurs, dtype=np.float32))

        self.dossier_cache.mkdir(parents=True, exist_ok=True)
        np.save(fichier_vecteurs, self.vecteurs, allow_pickle=False)
        fichier_morceaux.write_text(json.dumps([asdict(m) for m in self.morceaux], ensure_ascii=False),
                                    encoding="utf-8")
        journaliser("index_rag_calcule", morceaux=len(self.morceaux),
                    fiches=len({m.source for m in self.morceaux}),
                    duree_ms=round((time.perf_counter() - debut) * 1000))
        return self

    @staticmethod
    def _normaliser(matrice):
        normes = np.linalg.norm(matrice, axis=1, keepdims=True)
        return matrice / np.where(normes == 0, 1, normes)

    async def rechercher(self, question, nombre=5, fournisseur=None):
        """Renvoie [(score, Morceau)] du plus proche au moins proche. Filtre optionnel par fournisseur."""
        if self.vecteurs is None:
            raise RuntimeError("Index non construit : appeler d'abord construire().")
        candidats = range(len(self.morceaux))
        if fournisseur:
            cible = normaliser(fournisseur)
            candidats = [i for i in candidats
                         if cible in normaliser(self.morceaux[i].fournisseur) or cible in normaliser(self.morceaux[i].source)]
            if not candidats:
                return []
        candidats = list(candidats)

        vecteur = self._normaliser(np.asarray(await self.service.generate_embeddings([question]), dtype=np.float32))[0]
        scores = self.vecteurs[candidats] @ vecteur  # similarité cosinus (vecteurs normalisés)
        ordre = np.argsort(-scores)[:nombre]
        return [(float(scores[j]), self.morceaux[candidats[j]]) for j in ordre]


async def creer_index(service_embeddings=None):
    if service_embeddings is None:
        from app.config import creer_service_embeddings
        service_embeddings = creer_service_embeddings()
    return await IndexRag(service_embeddings).construire()


async def _demo(question):
    index = await creer_index()
    print(f"{len(index.morceaux)} morceaux indexés depuis {len({m.source for m in index.morceaux})} fiches.\n")
    for score, morceau in await index.rechercher(question):
        print(f"[{score:.3f}] {morceau.source} - {morceau.section}")


if __name__ == "__main__":
    asyncio.run(_demo(" ".join(sys.argv[1:]) or "Quels fournisseurs sont certifiés ISO 14001 ?"))
