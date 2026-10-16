# ui_streamlit.py
# Interface de chat : zone de saisie, fil de discussion, rendu Markdown,
# bouton « Nouvelle conversation » et affichage des outils appelés.
# Lancement : streamlit run ui_streamlit.py
#
# Semantic Kernel est asynchrone, Streamlit ne l'est pas : on garde UNE boucle asyncio
# dans un thread de fond, partagée par toutes les sessions (comme le Kernel et l'index RAG).
# Un asyncio.run() par message fermerait la boucle à laquelle le client Azure est rattaché
# (erreur « Event loop is closed » au 2e message).
import asyncio
import logging
import threading

import streamlit as st

from app.agent import nouvelle_conversation, preparer_agent, repondre
from app.journal import journaliser
from app.securite import LONGUEUR_MAX

QUESTIONS_EXEMPLES = [
    "Quels produits sont en rupture de stock ?",
    "Liste les produits Informatique à moins de 200 €.",
    "Quelle est la valeur du stock par fournisseur ?",
    "Supprime le produit n° 1.",
    "Quelles sont les conditions de paiement d'ErgoMobil ?",
    "Quels fournisseurs sont certifiés ISO 14001 ?",
    "Quel est le téléphone du fournisseur du switch 24 ports ?",
    "Quel fournisseur des produits en rupture a la moins bonne note interne ?",
]

st.set_page_config(page_title="Assistant Achats", page_icon="🛒")


# ---------- Ressources partagées (créées une seule fois pour toutes les sessions) ----------
@st.cache_resource
def boucle_asyncio():
    boucle = asyncio.new_event_loop()
    threading.Thread(target=boucle.run_forever, daemon=True, name="boucle-agent").start()
    return boucle


def executer(coroutine):
    """Exécute une coroutine sur la boucle de fond et attend son résultat."""
    return asyncio.run_coroutine_threadsafe(coroutine, boucle_asyncio()).result()


@st.cache_resource(show_spinner="Chargement de l'assistant et de l'index des fiches fournisseurs…")
def charger_agent():
    return executer(preparer_agent())


# ---------- État de la session (propre à chaque onglet du navigateur) ----------
def reinitialiser():
    st.session_state.fil = nouvelle_conversation()  # historique envoyé au modèle (tronqué)
    st.session_state.messages = []                  # messages affichés : role, contenu, outils, tokens


if "fil" not in st.session_state:
    reinitialiser()


def afficher_outils(outils, tokens):
    if not outils and not tokens:
        return
    with st.expander(f"🔧 Outils appelés ({len(outils)})"):
        for appel in outils:
            arguments = ", ".join(f"{cle}={valeur!r}" for cle, valeur in appel["arguments"].items())
            st.markdown(f"- `{appel['outil']}({arguments})` · {appel['duree_ms']} ms")
        if not outils:
            st.markdown("_Aucun outil : réponse directe du modèle._")
        if tokens:
            st.caption(f"Tokens : {tokens['entree']} en entrée, {tokens['sortie']} en sortie"
                       f" · coût estimé ≈ {tokens.get('cout_euros', 0):.5f} €")


# ---------- Barre latérale ----------
with st.sidebar:
    st.header("🛒 Assistant Achats")
    st.caption("Catalogue produits (base MySQL) et fiches PDF fournisseurs.")
    if st.button("➕ Nouvelle conversation", width="stretch", type="primary"):
        reinitialiser()
        st.rerun()
    st.divider()
    st.subheader("Exemples de questions")
    for i, exemple in enumerate(QUESTIONS_EXEMPLES):
        if st.button(exemple, key=f"exemple_{i}", width="stretch"):
            st.session_state.question_exemple = exemple


# ---------- Fil de discussion ----------
st.title("Assistant Achats")

try:
    agent = charger_agent()
except Exception as erreur:  # base, PDF ou Azure indisponibles au démarrage : rien de technique à l'écran
    journaliser("erreur_demarrage", logging.ERROR, erreur=f"{type(erreur).__name__}: {str(erreur)[:200]}")
    st.error("L'assistant est momentanément indisponible. Réessayez dans un instant.")
    st.stop()

if not st.session_state.messages:
    st.info("Posez une question sur les produits, les stocks ou les fournisseurs, "
            "ou choisissez un exemple dans la barre latérale.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["contenu"])
        if message["role"] == "assistant":
            afficher_outils(message["outils"], message["tokens"])

question = st.chat_input("Votre question…", max_chars=LONGUEUR_MAX)
question = question or st.session_state.pop("question_exemple", None)

if question:
    st.session_state.messages.append({"role": "user", "contenu": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("L'assistant réfléchit…"):
            texte, outils, tokens = executer(repondre(agent, st.session_state.fil, question))
        st.markdown(texte)
        afficher_outils(outils, tokens)
    st.session_state.messages.append({"role": "assistant", "contenu": texte, "outils": outils, "tokens": tokens})
