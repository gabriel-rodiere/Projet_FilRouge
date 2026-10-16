# Checklist de mise en production – Assistant IA Catalogue & Fournisseurs

Ce document prépare une future mise en production de l'assistant. Pour chaque critère du cahier des charges, il indique
**comment il est appliqué** dans le code ou le pipeline, avec une **preuve** (extrait de code, test, exécution du pipeline),
ou, lorsqu'il dépend de l'hébergement, **la recommandation retenue**.

| Légende | Signification |
|---|---|
| ✅ | Appliqué dans le code ou le pipeline, avec preuve |
| 🏗️ | Dépend de l'hébergement : recommandation retenue |
| ⚠️ | Appliqué avec une limite connue, documentée en [section 6](#6-limites-connues-et-actions-avant-la-mise-en-production) |

**Architecture cible recommandée :** Azure App Service (ou Container Apps) pour l'interface Streamlit, Azure Database for
MySQL – Flexible Server, Azure OpenAI (un déploiement de chat *mini* + un déploiement d'embeddings), Azure Key Vault pour les
secrets, Application Insights pour les logs, le tout dans un groupe de ressources dédié.

**Pipeline de référence :** [exécution n° 38914211652](https://github.com/gabriel-rodiere/Projet_FilRouge/actions/runs/38914211652)
(push sur `main`, toutes les étapes vertes). 51 tests unitaires, couverture ≈ 82 %.

---

## 1. Sécurité

| # | Critère | Statut | Comment c'est appliqué | Preuve |
|---|---|:---:|---|---|
| S1 | Secrets hors du code : `.env` ignoré par git, secrets GitHub pour le pipeline | ✅ | Les secrets sont lus dans `.env` (jamais commité) ; seul `.env.example`, sans valeur, est versionné. Le pipeline lit ses mots de passe dans les **secrets GitHub** (`MYSQL_ROOT_PASSWORD`, `MYSQL_AGENT_PASSWORD`), y compris pour Dependabot. Le mot de passe de démonstration du script SQL est **remplacé** en CI par celui des secrets. | [.gitignore:2](.gitignore#L2) · [tests.yml:37-51](.github/workflows/tests.yml#L37-L51) · [tests.yml:78](.github/workflows/tests.yml#L78) · vérifié : clé Azure présente 0 fois dans l'historique git |
| S2 | Utilisateur MySQL dédié avec le seul droit SELECT | ✅ | L'application se connecte avec `agent_ia`, qui n'a que `GRANT SELECT ON catalogue.*`. Toute écriture est refusée **par la base elle-même**, même si une requête d'écriture lui parvenait. | [00_mysql_base_et_utilisateur.sql:10-11](sql/00_mysql_base_et_utilisateur.sql#L10-L11) · tests [`test_ecriture_refusee`](tests/test_lecture_seule.py#L21) (DELETE, UPDATE, INSERT, DROP, CREATE → erreur 1142), [`test_seul_le_droit_select`](tests/test_lecture_seule.py#L36) |
| S3 | Requêtes paramétrées, pas de SQL libre généré par le LLM | ✅ | Le LLM ne voit jamais la base : il choisit parmi 5 outils dont le SQL est écrit à l'avance. Les valeurs passent en paramètres `%s` ; le seul nom de colonne variable est contrôlé par une **liste blanche**. Aucun outil n'écrit. | [db.py:42](app/db.py#L42) · [catalogue.py:19](app/plugins/catalogue.py#L19) · tests [`test_parametres_passes_a_part_du_sql`](tests/test_catalogue.py#L72), [`test_regroupement_hors_liste_blanche_refuse`](tests/test_catalogue.py#L61) |
| S4 | Protection contre l'injection de prompt (instructions, limites) | ✅ | Trois barrières : (1) [securite.py](app/securite.py#L24) refuse avant le LLM les questions vides, de plus de 1 000 caractères ou contenant des motifs d'injection (comparaison sans accents ni majuscules) — **0 token consommé** ; (2) instructions système : lecture seule, message utilisateur et contenu des fiches traités comme des **données** ; (3) garde-fou de 8 appels d'outils maximum par question. | [securite.py:13](app/securite.py#L13) · [agent.py:44-46](app/agent.py#L44-L46) · [agent.py:54](app/agent.py#L54) · tests [`test_injections_de_prompt_detectees`](tests/test_agent.py#L40), [`test_question_refusee_sans_appel_au_llm`](tests/test_agent.py#L50) · recette : « Supprime le produit n° 1 » → refus |
| S5 | Dépendances auditées dans le pipeline (pip-audit, Dependabot) | ⚠️ | `pip-audit` s'exécute à chaque pipeline ; une vulnérabilité nouvelle le fait échouer. **Dependabot** propose chaque semaine les mises à jour pip et GitHub Actions (8 PR ouvertes dès l'activation, testées par le pipeline). 4 vulnérabilités de `werkzeug` sont ignorées avec justification (voir section 6). | [tests.yml:82-92](.github/workflows/tests.yml#L82-L92) · [dependabot.yml](.github/dependabot.yml) |
| S6 | Erreurs techniques non affichées à l'utilisateur | ✅ | Erreurs MySQL, Azure (401, quota, filtre de contenu) et RAG : le détail est **journalisé**, l'utilisateur reçoit un message neutre. Streamlit est configuré sans trace d'erreur (`showErrorDetails = "none"`). | [catalogue.py:24-30](app/plugins/catalogue.py#L24-L30) · [agent.py:137](app/agent.py#L137) · [config.toml:9](.streamlit/config.toml#L9) · tests [`test_erreur_de_base_masquee`](tests/test_catalogue.py#L82), [`test_erreur_azure_masquee_a_l_utilisateur`](tests/test_agent.py#L57), [`test_outil_masque_les_erreurs_techniques`](tests/test_rag.py#L106) |

Extrait – requête paramétrée et liste blanche ([app/plugins/catalogue.py](app/plugins/catalogue.py)) :

```python
REGROUPEMENTS = ("categorie", "fournisseur")   # seuls noms de colonne acceptés
...
if regroupement not in REGROUPEMENTS:
    return "Regroupement impossible. Valeurs possibles : " + ", ".join(REGROUPEMENTS)
...
sql += " AND prix <= %s"          # la valeur part en paramètre, jamais dans le texte SQL
parametres.append(prix_max)
```

**Recommandations pour l'hébergement :**
- 🏗️ Remplacer la clé API par une **identité managée Entra ID** (aucune clé à stocker), ou à défaut stocker la clé dans **Azure Key Vault** (méthode vue dans `AgentIA_Prod/p1_secrets.py`).
- 🏗️ Protéger l'accès à l'interface par l'**authentification App Service (Entra ID)** : Streamlit n'a pas d'authentification native.
- 🏗️ Ajouter une **limitation de débit** par utilisateur (Azure API Management ou limiteur applicatif comme `LimiteurDeDebit` de `p2_securite.py`).
- 🏗️ MySQL : accès par réseau privé uniquement, TLS obligatoire, mot de passe `agent_ia` généré et stocké dans Key Vault.

---

## 2. Optimisation et performance

| # | Critère | Statut | Comment c'est appliqué | Preuve |
|---|---|:---:|---|---|
| O1 | Index RAG calculé une seule fois (cache, pas à chaque requête) | ✅ | Les 40 morceaux (8 fiches × 5 sections) sont vectorisés une seule fois puis enregistrés dans `cache/`. L'empreinte (contenu des PDF + modèle + version du découpage) recalcule l'index **uniquement** si une fiche change. Chargement depuis le cache : **0,04 s** ; recherche : ≈ 0,4 s. | [rag.py:127](app/rag.py#L127) · [rag.py:143](app/rag.py#L143) · tests [`test_index_calcule_une_seule_fois_puis_cache`](tests/test_rag.py#L49), [`test_index_recalcule_si_une_fiche_change`](tests/test_rag.py#L59) |
| O2 | Résultats SQL limités (LIMIT), historique de conversation tronqué | ✅ | Toutes les requêtes de liste ont `LIMIT 50`. L'historique est tronqué aux 20 derniers messages (`HISTORIQUE_MAX_MESSAGES`), **sans séparer un appel d'outil de son résultat** (`ChatHistoryTruncationReducer` de Semantic Kernel). | [catalogue.py:16](app/plugins/catalogue.py#L16) · [agent.py:108](app/agent.py#L108) · [agent.py:145](app/agent.py#L145) · tests [`test_resultats_limites_par_LIMIT`](tests/test_catalogue.py#L44), [`test_historique_tronque`](tests/test_agent.py#L63) |
| O3 | Modèle adapté (ex. mini), max_tokens et température maîtrisés | ✅ | Modèle **`gpt-5.4-mini`**. Réponse limitée par `max_completion_tokens=800` (les modèles GPT-5 refusent `max_tokens`, testé), `temperature=0.2` pour des réponses factuelles. Les deux sont réglables dans `.env`. | [agent.py:86-87](app/agent.py#L86-L87) · [.env.example](.env.example) |
| O4 | Ressources partagées (Kernel, pool de connexions MySQL) | ✅ | **Pool de 5 connexions** MySQL créé une fois et réutilisé. Dans l'interface, le Kernel, l'index RAG, l'agent et la boucle asyncio sont créés **une seule fois pour toutes les sessions** (`st.cache_resource`) ; seul l'historique est propre à chaque utilisateur. Le chat et les embeddings partagent le même client HTTP Azure. | [db.py:29-34](app/db.py#L29-L34) · [ui_streamlit.py:35](ui_streamlit.py#L35) · [ui_streamlit.py:47-48](ui_streamlit.py#L47-L48) |
| O5 | Index MySQL sur les colonnes filtrées | ⚠️ | Index sur `fournisseur` et `categorie`, les colonnes de filtre et de regroupement les plus utilisées. | [01_schema.sql:18-19](sql/01_schema.sql#L18-L19) |
| O6 | Pipeline avec cache pip | ✅ | `actions/setup-python` avec `cache: pip`, indexé sur `requirements.txt`. | [tests.yml:62-63](.github/workflows/tests.yml#L62-L63) |

**Optimisation mesurée pendant le projet :** pour « Quels fournisseurs sont certifiés ISO 14001 ? », l'agent faisait au départ
une recherche par fournisseur (9 appels d'outils, 8 900 tokens). Après précision des instructions (« une seule recherche
globale »), il en fait 2 pour 4 600 tokens, avec la même réponse : **coût divisé par deux**.

**Recommandations :**
- 🏗️ Ajouter des index sur `prix` et `stock` (filtres `prix_min/prix_max` et `stock_faible`) : inutile avec 38 produits, utile à partir de quelques milliers.
- 🏗️ En production, remplacer le cache fichier de l'index par une base vectorielle managée (Azure AI Search) si le nombre de fiches dépasse quelques centaines.
- 🏗️ Démarrage à froid ≈ 25 s (import de Semantic Kernel) : garder au moins une instance active (*Always On* sur App Service).

---

## 3. Logs et observabilité

| # | Critère | Statut | Comment c'est appliqué | Preuve |
|---|---|:---:|---|---|
| L1 | Logs structurés : question, outils appelés, durée, erreurs | ✅ | Une ligne **JSON** par événement : `question` (question et réponse tronquées, outils appelés, durée, tokens, coût), `appel_outil` (niveau DEBUG : outil, arguments, durée), `question_refusee`, `erreur_bd`, `erreur_agent`, `erreur_rag`, `index_rag_calcule` / `index_rag_cache`. | [agent.py:148](app/agent.py#L148) · [journal.py:70](app/journal.py#L70) · test [`test_ligne_json_structuree`](tests/test_journal.py#L39) |
| L2 | Niveau de log et fichier configurables, avec rotation | ✅ | `LOG_LEVEL` et `LOG_FILE` dans `.env`. `RotatingFileHandler` : 1 Mo par fichier, 5 fichiers conservés. | [journal.py:33](app/journal.py#L33) · [journal.py:38](app/journal.py#L38) |
| L3 | Suivi des tokens consommés par requête | ✅ | Les tokens de **tous** les appels au modèle d'une question (y compris ceux qui demandent des outils) sont additionnés et journalisés. Ils s'affichent aussi sous chaque réponse dans l'interface. | [agent.py:112-120](app/agent.py#L112-L120) · test [`test_tokens_additionnes_sur_tous_les_appels`](tests/test_agent.py#L72) |
| L4 | Aucune donnée sensible ni clé dans les logs | ✅ | Questions, réponses et arguments **tronqués à 80 caractères**. Avant écriture, chaque ligne passe par `masquer_secrets` : la clé Azure et le mot de passe MySQL réels, ainsi que tout motif `api_key=…`, `password: …`, `Bearer …`, sont remplacés par `***`. | [journal.py:20](app/journal.py#L20) · [journal.py:52](app/journal.py#L52) · tests [`test_cles_et_mots_de_passe_masques_dans_le_journal`](tests/test_journal.py#L18), [`test_textes_tronques`](tests/test_journal.py#L34) · vérifié : 0 occurrence de la clé et du mot de passe dans `logs/` |
| L5 | Rapport de tests et couverture de code publiés par le pipeline | ✅ | Le résumé (tests réussis / échoués, couverture par fichier) s'affiche sur la page du pipeline ; `rapport-tests.xml`, `coverage.xml` et le rapport HTML sont publiés en artefact. Seuil minimal de couverture : 75 %. | [tests.yml:99](.github/workflows/tests.yml#L99) · [tests.yml:104-123](.github/workflows/tests.yml#L104-L123) · [tests.yml:128](.github/workflows/tests.yml#L128) |

Exemple de ligne réelle du journal (retours à la ligne ajoutés pour la lecture) :

```json
{"horodatage": "2026-10-16T16:32:16", "niveau": "INFO", "evenement": "question",
 "question": "Quel est le téléphone du fournisseur du switch 24 ports ?",
 "reponse": "| Fournisseur | Téléphone |\n|---|---|\n| NetLink Systèmes | 03 20 00 50 05 |\n\nSou...",
 "outils": ["rechercher_produits", "rechercher_fiches"], "duree_ms": 3668,
 "tokens_entree": 3856, "tokens_sortie": 118, "cout_euros": 0.004328}
```

**Recommandations :**
- 🏗️ Envoyer les logs vers **Application Insights** (`azure-monitor-opentelemetry`, comme dans `p3_observabilite.py`) et créer des alertes sur : taux d'erreur, latence > 10 s, événements `question_refusee` répétés.

---

## 4. Facturation et coûts

| # | Critère | Statut | Comment c'est appliqué | Preuve |
|---|---|:---:|---|---|
| C1 | Aucun appel payant dans le pipeline (tests sans Azure OpenAI) | ✅ | Les tests utilisent un **faux service d'embeddings** et de **faux agents**. Le pipeline ne reçoit **aucune** variable Azure : un appel payant y est impossible. | [conftest.py](tests/conftest.py) · [tests.yml:46-51](.github/workflows/tests.yml#L46-L51) |
| C2 | Coût estimé à partir des tokens journalisés | ✅ | Coût de chaque question calculé à partir des prix au million de tokens (`.env`) et journalisé (`cout_euros`). `python -m app.journal` fait le **bilan** du journal (rotation incluse) : questions, refus, erreurs, tokens, coût, durées, outils. | [journal.py:63](app/journal.py#L63) · [journal.py:79](app/journal.py#L79) · tests [`test_cout_estime_a_partir_des_tokens`](tests/test_journal.py#L46), [`test_bilan_du_journal`](tests/test_journal.py#L53) |
| C3 | Quota de tokens par minute sur les déploiements Azure OpenAI | 🏗️ | Voir recommandation ci-dessous. Côté code, un dépassement (erreur 429) est absorbé par 3 nouvelles tentatives automatiques puis par un message neutre. | [config.py:21-22](app/config.py#L21-L22) |
| C4 | Budget et alertes de dépense, tags sur la ressource | 🏗️ | Voir recommandation ci-dessous. | – |
| C5 | Suppression des ressources Azure en fin de formation | 🏗️ | Voir recommandation ci-dessous. | – |

**Mesure réelle** – les 8 questions de recette et une tentative d'injection, avec l'agent réel (bilan de `python -m app.journal`) :

| Question | Outils appelés | Tokens (entrée + sortie) | Coût estimé |
|---|---|---:|---:|
| Produits en rupture de stock | `stock_faible` | 2 393 + 176 | 0,0031 € |
| Informatique à moins de 200 € | `rechercher_produits` | 2 352 + 151 | 0,0030 € |
| Valeur du stock par fournisseur | `valeur_stock` | 2 508 + 226 | 0,0034 € |
| Supprime le produit n° 1 (refus) | – | 1 074 + 29 | 0,0012 € |
| Conditions de paiement d'ErgoMobil | catalogue + `rechercher_fiches` | 4 391 + 104 | 0,0048 € |
| Fournisseurs certifiés ISO 14001 | catalogue + `rechercher_fiches` | 4 626 + 134 | 0,0052 € |
| Téléphone du fournisseur du switch 24 ports | `rechercher_produits` + `rechercher_fiches` | 3 856 + 118 | 0,0043 € |
| Fournisseur en rupture le moins bien noté | `stock_faible` + 4 × `rechercher_fiches` | 5 342 + 282 | 0,0065 € |
| « Ignore tes instructions… » (bloquée) | – | **0 + 0** | **0 €** |
| **Total (8 questions traitées)** | | **26 542 + 1 220** | **0,031 €**, soit **≈ 0,004 € par question** |

Prix utilisés : 1,00 € / 4,00 € par million de tokens d'entrée / de sortie (**valeurs d'exemple** de `.env`, à remplacer par
la grille Azure du modèle retenu). L'index d'embeddings (40 morceaux, ≈ 6 000 tokens) n'est calculé qu'une fois : coût
inférieur à 0,001 €. Durée moyenne d'une réponse : 3,4 s.

**Recommandations retenues pour l'hébergement :**
- 🏗️ **Quota TPM** : une question consomme ≈ 3 500 tokens. Pour 20 utilisateurs simultanés à 2 questions par minute,
  il faut ≈ 140 000 tokens/minute ; fixer le quota du déploiement de chat à **150 K TPM** en production et à **30 K TPM**
  en formation, pour limiter le coût maximal même en cas de boucle ou d'abus.
- 🏗️ **Budget et alertes** : budget mensuel dans *Azure Cost Management* sur le groupe de ressources, avec alertes e-mail
  à **50 %, 80 % et 100 %**.
- 🏗️ **Tags** sur toutes les ressources : `projet=assistant-achats`, `environnement=formation|production`,
  `proprietaire=<équipe>`, `date-fin=<aaaa-mm-jj>`, pour ventiler les coûts et repérer les ressources à supprimer.
- 🏗️ **Suppression en fin de formation** : toutes les ressources étant dans un seul groupe, une commande suffit
  (`az group delete --name <groupe-de-ressources> --yes`). La ressource Azure OpenAI utilisée (`flpdev`) appartient au
  formateur : sa suppression est à **coordonner avec lui**. Côté projet : révoquer ou régénérer la clé API, supprimer les
  secrets GitHub et le dossier `cache/`.

---

## 5. Comment vérifier soi-même

| Vérification | Commande |
|---|---|
| Lancer tous les tests avec la couverture | `pytest --cov=app` |
| Vérifier le refus d'écriture en base | `pytest tests/test_lecture_seule.py -v` |
| Bilan des coûts et de l'usage | `python -m app.journal` |
| Recherche RAG seule (sans le LLM) | `python -m app.rag "certifications ISO 14001"` |
| Voir le pipeline et son rapport | onglet **Actions** du dépôt, puis le dernier run du workflow **Tests** |

---

## 6. Limites connues et actions avant la mise en production

| Limite | Risque | Action |
|---|---|---|
| `werkzeug 3.1.1` vulnérable (4 alertes ignorées dans pip-audit) | Faible : imposé par semantic-kernel 1.45 via `openapi-core < 0.20`, utilisé uniquement par l'intégration Flask d'openapi-core, que l'application n'appelle pas | Retirer les `--ignore-vuln` dès que Dependabot propose une version de semantic-kernel qui lève la contrainte |
| Mot de passe de démonstration de `agent_ia` écrit dans `sql/00_mysql_base_et_utilisateur.sql` (script fourni) | Réservé au poste de développement ; en CI il est déjà remplacé par un secret GitHub | En production : créer l'utilisateur avec un mot de passe généré, stocké dans Key Vault |
| Prix des tokens dans `.env` = valeurs d'exemple | Coût estimé indicatif | Renseigner la grille tarifaire réelle du modèle déployé |
| Détection d'injection par motifs | Une formulation inédite peut passer la première barrière | Les deux autres barrières (instructions, utilisateur en lecture seule) restent actives ; en production, ajouter **Azure AI Content Safety – Prompt Shields** |
| Pas d'authentification ni de limite de débit dans l'interface | Usage non contrôlé si l'URL est publique | Authentification App Service (Entra ID) et limitation de débit (section 1) |
