# Assistant IA Catalogue & Fournisseurs

Assistant conversationnel destiné au service Achats. Il répond en français aux
questions sur le catalogue produits et les fournisseurs en s'appuyant sur les
données MySQL et sur les fiches fournisseurs au format PDF.

Le projet utilise Semantic Kernel et Azure OpenAI pour l'agent conversationnel
et les embeddings. L'interface est réalisée avec Streamlit.

## Fonctionnalités

- Recherche et filtres dans le catalogue : produits, catégories, prix,
  fournisseurs et niveaux de stock.
- Calcul de statistiques de stock par catégorie ou fournisseur.
- Recherche sémantique dans les fiches PDF pour trouver les coordonnées,
  conditions commerciales, certifications, garanties et autres informations
  fournisseurs.
- Réponses sourcées et affichage des outils appelés.
- Agent en lecture seule : les requêtes SQL sont paramétrées et le compte MySQL
  de l'agent doit disposer uniquement du droit `SELECT`.
- Contrôle des entrées utilisateur, notamment de leur longueur et de motifs
  courants d'injection de prompt.
- Journalisation structurée des événements, outils, durées, tokens et coûts
  estimés.

Les données fournies sont fictives et destinées à un usage pédagogique. Le
catalogue de démonstration contient 38 produits et les fiches PDF couvrent
8 fournisseurs.

## Prérequis

- Python 3.12 (version utilisée par la CI).
- MySQL 8 ou MariaDB compatible, pour les fonctionnalités catalogue.
- Un accès Azure OpenAI avec un déploiement de chat et un déploiement
  d'embeddings.
- Les fiches PDF présentes dans `fiches_fournisseurs/`.

## Installation

Depuis le dossier du projet, dans PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Renseignez ensuite les paramètres locaux dans `.env`. Il doit notamment
contenir l'URL de la ressource Azure OpenAI, l'accès à cette ressource, les noms
des déploiements de chat et d'embeddings, ainsi que la configuration de MySQL.
Les noms des déploiements doivent correspondre à ceux configurés dans votre
ressource Azure.

Le fichier `.env` est réservé à votre environnement local et ne doit jamais
être ajouté au dépôt. `.env.example` fournit la liste des paramètres attendus,
sans valeur de configuration personnelle.

## Préparer MySQL

Les scripts d'initialisation sont à exécuter dans cet ordre depuis la racine du
projet :

```powershell
Get-Content -Raw .\sql\00_mysql_base_et_utilisateur.sql | mysql -u root -p
Get-Content -Raw .\sql\01_schema.sql | mysql -u root -p catalogue
Get-Content -Raw .\sql\02_donnees.sql | mysql -u root -p catalogue
```

Le premier script crée la base et un compte de démonstration en lecture seule.
Avant de l'utiliser, adaptez la configuration du compte à votre environnement
et définissez dans `.env` les mêmes paramètres de connexion. N'utilisez pas les
valeurs de démonstration dans un environnement partagé ou de production.

**Attention :** `sql/01_schema.sql` supprime puis recrée la table `produits`.
Ces scripts sont prévus pour initialiser une base de développement, pas pour
une base contenant des données à conserver.

## Lancer l'application

```powershell
streamlit run ui_streamlit.py
```

Streamlit affiche l'adresse locale de l'interface dans le terminal. Au premier
démarrage, l'application lit les fiches PDF et peut appeler le déploiement
d'embeddings pour créer l'index RAG. Cet index est ensuite conservé dans le
répertoire local `cache/` et recalculé si les fiches ou le modèle changent.

## Tests

Lancer l'ensemble des tests :

```powershell
pytest
```

Les tests du RAG utilisent un faux service d'embeddings et ne font pas d'appel
à Azure OpenAI. Les tests qui nécessitent MySQL sont identifiés par le marqueur
`bd` : si la base n'est pas accessible, ils sont ignorés en local. Pour exécuter
ces tests, préparez la base avec les scripts ci-dessus. En CI, l'absence de la
base fait échouer les tests concernés.

Pour exécuter uniquement les tests ne nécessitant pas MySQL :

```powershell
pytest -m "not bd"
```

Pour produire un rapport local de couverture :

```powershell
pytest --cov=app --cov-report=term --cov-report=html
```

## Intégration continue

Le workflow GitHub Actions `.github/workflows/tests.yml` s'exécute lors des
pushs et pull requests vers `main`, ainsi qu'à la demande. Il démarre un service
MySQL de test, installe les dépendances, lance `pip-audit` et exécute les tests
avec une couverture minimale configurée à 75 %. Les rapports de tests et de
couverture sont publiés comme résumé du workflow et comme artefacts.

Les tests du workflow ne font pas appel à Azure OpenAI. Dependabot surveille
chaque semaine les dépendances Python et les actions GitHub.

## Structure du projet

```text
app/
  agent.py             Agent Semantic Kernel et orchestration des outils
  config.py            Configuration des services Azure OpenAI
  db.py                Accès au catalogue MySQL
  journal.py           Journalisation et estimation des coûts
  rag.py               Indexation et recherche sémantique dans les PDF
  securite.py          Validation des entrées utilisateur
  plugins/
    catalogue.py       Outils de recherche du catalogue
    fiches.py          Outil de recherche dans les fiches fournisseurs
sql/                   Scripts de création et de peuplement de MySQL
tests/                 Tests unitaires et tests d'intégration MySQL
fiches_fournisseurs/   Fiches PDF utilisées par le RAG
ui_streamlit.py        Interface de chat Streamlit
```
