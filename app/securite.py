# securite.py
# Barrières avant l'appel au LLM (repris de AgentIA_Prod/p2_securite.py) :
#   - entrée vide ou trop longue refusée
#   - détection des tentatives d'injection de prompt
