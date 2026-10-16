# test_journal.py
# Logs structurés : secrets masqués, textes tronqués, coût estimé, bilan à partir du journal.
import json
import logging
from pathlib import Path

from app import journal
from app.journal import bilan, estimer_cout, journaliser, masquer_secrets, tronquer


def lignes_du_journal():
    for gestionnaire in journal.log.handlers:
        gestionnaire.flush()
    fichier = Path(journal.log.handlers[0].baseFilename)
    return [json.loads(ligne) for ligne in fichier.read_text(encoding="utf-8").splitlines()]


def test_cles_et_mots_de_passe_masques_dans_le_journal(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "cle-azure-tres-secrete-123")
    monkeypatch.setenv("MYSQL_PASSWORD", "MotDePasseBase!")
    journaliser("erreur_test", logging.ERROR,
                erreur="401 avec cle-azure-tres-secrete-123, connexion MotDePasseBase! refusée, api_key=abc123")
    derniere = json.dumps(lignes_du_journal()[-1], ensure_ascii=False)
    for secret in ("cle-azure-tres-secrete-123", "MotDePasseBase!", "abc123"):
        assert secret not in derniere
    assert "***" in derniere


def test_motifs_de_secrets():
    assert masquer_secrets("password: azerty ; token=xyz ; Authorization: Bearer eyJhbGci") == \
        "password: *** ; token=*** ; Authorization: Bearer ***"


def test_textes_tronques():
    assert tronquer("a" * 200) == "a" * 80 + "..."
    assert tronquer("court") == "court"


def test_ligne_json_structuree():
    journaliser("question", question="Produits en rupture ?", outils=["stock_faible"], duree_ms=42)
    ligne = lignes_du_journal()[-1]
    assert ligne["evenement"] == "question" and ligne["niveau"] == "INFO"
    assert {"horodatage", "question", "outils", "duree_ms"} <= ligne.keys()


def test_cout_estime_a_partir_des_tokens(monkeypatch):
    monkeypatch.setenv("PRIX_ENTREE_1M_TOKENS", "0.75")
    monkeypatch.setenv("PRIX_SORTIE_1M_TOKENS", "4.50")
    assert estimer_cout(1_000_000, 0) == 0.75
    assert estimer_cout(2000, 100) == round((2000 * 0.75 + 100 * 4.50) / 1_000_000, 6)


def test_bilan_du_journal(tmp_path):
    fichier = tmp_path / "assistant.jsonl"
    evenements = [
        {"evenement": "question", "tokens_entree": 1000, "tokens_sortie": 100, "cout_euros": 0.0015,
         "duree_ms": 2000, "outils": ["stock_faible"]},
        {"evenement": "question", "tokens_entree": 3000, "tokens_sortie": 200, "cout_euros": 0.0038,
         "duree_ms": 4000, "outils": ["stock_faible", "rechercher_fiches"]},
        {"evenement": "question_refusee", "niveau": "WARNING"},
        {"evenement": "erreur_agent", "niveau": "ERROR"},
    ]
    fichier.write_text("\n".join(json.dumps(e) for e in evenements), encoding="utf-8")
    (tmp_path / "assistant.jsonl.1").write_text(json.dumps(evenements[0]), encoding="utf-8")  # fichier de rotation

    b = bilan(fichier)
    assert (b["questions"], b["refusees"], b["erreurs"]) == (3, 1, 1)
    assert (b["tokens_entree"], b["tokens_sortie"]) == (5000, 400)
    assert round(b["cout_euros"], 4) == 0.0068
    assert b["outils"]["stock_faible"] == 3
