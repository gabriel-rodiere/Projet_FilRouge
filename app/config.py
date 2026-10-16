# config.py
# Crée le "Kernel" de Semantic Kernel, connecté aux deux déploiements Azure OpenAI :
#   - un modèle de chat       (CHAT_DEPLOYMENT)      -> l'agent
#   - un modèle d'embeddings  (EMBEDDING_DEPLOYMENT) -> le RAG sur les fiches PDF
# Repris de AgentIA_SemanticKernel/config.py, avec le service d'embeddings en plus.
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion, OpenAITextEmbedding

load_dotenv()


def creer_client():
    # API v1 d'Azure OpenAI, en version "Async" car Semantic Kernel travaille en asynchrone.
    return AsyncOpenAI(
        base_url=os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/") + "/openai/v1/",
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        timeout=30,      # on n'attend pas plus de 30 secondes une réponse
        max_retries=3,   # en cas d'erreur 429 (quota) ou 5xx, 3 nouvelles tentatives automatiques
    )


def creer_service_embeddings(client=None):
    return OpenAITextEmbedding(
        ai_model_id=os.environ["EMBEDDING_DEPLOYMENT"],  # le NOM DU DÉPLOIEMENT
        async_client=client or creer_client(),
    )


def creer_kernel():
    client = creer_client()
    kernel = Kernel()
    kernel.add_service(OpenAIChatCompletion(
        ai_model_id=os.environ["CHAT_DEPLOYMENT"],  # le NOM DU DÉPLOIEMENT
        async_client=client,
    ))
    kernel.add_service(creer_service_embeddings(client))
    return kernel
