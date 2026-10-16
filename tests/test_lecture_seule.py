# test_lecture_seule.py
# L'utilisateur agent_ia n'a que le droit SELECT : toute écriture est refusée PAR LA BASE,
# même si une requête d'écriture arrivait jusqu'à elle.
import pytest
from mysql.connector import errors

from app.db import executer_requete, get_pool

pytestmark = pytest.mark.bd

ECRITURES = [
    "DELETE FROM produits WHERE id = 1",
    "UPDATE produits SET prix = 0 WHERE id = 1",
    "INSERT INTO produits (id, libelle, categorie, prix, stock, fournisseur) VALUES (999, 'x', 'x', 1, 1, 'x')",
    "DROP TABLE produits",
    "CREATE TABLE piratage (id INT)",
]


@pytest.mark.parametrize("sql", ECRITURES, ids=lambda sql: sql.split()[0])
def test_ecriture_refusee(base_disponible, sql):
    connexion = get_pool().get_connection()
    try:
        with pytest.raises(errors.ProgrammingError) as erreur:
            connexion.cursor().execute(sql)
        assert erreur.value.errno in (1142, 1044)  # « command denied to user » / « access denied »
    finally:
        connexion.rollback()
        connexion.close()


def test_catalogue_intact_apres_tentatives(base_disponible):
    assert executer_requete("SELECT COUNT(*) AS n FROM produits") == [{"n": 38}]


def test_seul_le_droit_select(base_disponible):
    droits = " ".join(next(iter(ligne.values())) for ligne in executer_requete("SHOW GRANTS"))
    assert "GRANT SELECT ON `catalogue`.*" in droits
    for droit in ("INSERT", "UPDATE", "DELETE", "DROP", "ALL PRIVILEGES"):
        assert droit not in droits
