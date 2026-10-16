# rag.py
# RAG sur les fiches fournisseurs :
#   1. lire tous les PDF du dossier FICHES_DIR (pypdf)
#   2. découper par section, chaque morceau préfixé par la raison sociale du fournisseur
#   3. calculer les embeddings UNE SEULE FOIS (cache dans RAG_CACHE_DIR)
#   4. rechercher les morceaux les plus proches d'une question (similarité cosinus)
# Le service d'embeddings est passé en paramètre : les tests utilisent un faux service, sans Azure.
