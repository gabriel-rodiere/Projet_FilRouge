# conftest.py
# Fixtures communes aux tests : connexion MySQL de test, faux service d'embeddings.
# Les tests n'appellent JAMAIS Azure OpenAI.
import os
import re
import tempfile
import zlib
from pathlib import Path

import numpy as np
import pytest

# Les logs des tests vont dans un dossier temporaire, pas dans logs/ (à faire AVANT d'importer app.*)
os.environ["LOG_FILE"] = str(Path(tempfile.mkdtemp(prefix="logs_tests_")) / "tests.jsonl")

from app.rag import normaliser  # noqa: E402

DOSSIER_FICHES = Path(__file__).parent.parent / "fiches_fournisseurs"


class FauxServiceEmbeddings:
    """Remplace Azure OpenAI : un « sac de mots » haché dans un vecteur de 512 dimensions.
    Deux textes qui partagent des mots ont des vecteurs proches : suffisant pour tester la recherche."""

    ai_model_id = "faux-embeddings"
    DIMENSION = 512

    def __init__(self):
        self.nb_appels = 0
        self.nb_textes = 0

    async def generate_embeddings(self, textes):
        self.nb_appels += 1
        self.nb_textes += len(textes)
        vecteurs = np.zeros((len(textes), self.DIMENSION), dtype=np.float32)
        for i, texte in enumerate(textes):
            for mot in re.findall(r"\w{3,}", normaliser(texte)):
                vecteurs[i, zlib.crc32(mot.encode()) % self.DIMENSION] += 1.0
        return vecteurs


class ServiceEnPanne:
    ai_model_id = "en-panne"

    async def generate_embeddings(self, textes):
        raise ConnectionError("Azure injoignable : https://secret.example api_key=XXXX")


@pytest.fixture
def faux_service():
    return FauxServiceEmbeddings()


@pytest.fixture
def dossier_fiches():
    return DOSSIER_FICHES


@pytest.fixture(scope="session")
def base_disponible():
    """Vérifie que la base de test répond. En CI, une base absente est une ERREUR ; en local, on saute ces tests."""
    from app.db import executer_requete
    try:
        executer_requete("SELECT 1")
    except Exception as erreur:
        message = f"Base MySQL indisponible ({type(erreur).__name__})"
        if os.getenv("CI"):
            pytest.fail(message)
        pytest.skip(message + " : démarrez MySQL pour lancer ces tests.")
    return True
