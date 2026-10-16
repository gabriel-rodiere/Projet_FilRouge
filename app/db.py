# db.py
# Accès à la base MySQL "catalogue", en LECTURE SEULE (utilisateur agent_ia, droit SELECT uniquement).
#   - un pool de connexions partagé (au lieu d'une connexion par requête)
#   - uniquement des requêtes paramétrées (%s), jamais de SQL généré par le LLM
# Repris de AgentIA_MySQL/agent_bd.py (executer_requete).
import os
from decimal import Decimal

from dotenv import load_dotenv
from mysql.connector import pooling

load_dotenv()

_pool = None


def config_bd():
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],          # l'utilisateur "agent_ia" : lecture seule
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.getenv("MYSQL_DATABASE", "catalogue"),
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",         # comparaisons insensibles à la casse et aux accents
    }


def get_pool():
    """Crée le pool au premier appel, puis le réutilise (ressource partagée)."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(pool_name="catalogue", pool_size=5, **config_bd())
    return _pool


def executer_requete(sql, parametres=()):
    """Exécute une requête SELECT paramétrée et renvoie la liste des lignes (dictionnaires)."""
    connexion = get_pool().get_connection()
    try:
        curseur = connexion.cursor(dictionary=True)  # chaque ligne = un dictionnaire {colonne: valeur}
        curseur.execute(sql, parametres)              # les %s sont remplacés EN SÉCURITÉ par les paramètres
        lignes = curseur.fetchall()
        curseur.close()
    finally:
        connexion.close()                             # rend la connexion au pool, même en cas d'erreur
    # Les DECIMAL de MySQL deviennent des float, lisibles en JSON
    return [{cle: float(val) if isinstance(val, Decimal) else val for cle, val in ligne.items()}
            for ligne in lignes]
