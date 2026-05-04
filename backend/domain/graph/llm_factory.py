"""
LLM Factory — Shared LLM instance builder for all graph nodes.

Supports:
  - Google Gemini 2.5 Flash via Vertex AI (cloud, default — uses GCP credits)
  - Ollama via OpenAI-compatible API (local, opt-in via USE_LOCAL_LLM=true)
"""

import os
import logging

from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI

logger = logging.getLogger("I-Way-Twin")


def build_llm():
    """Build the LLM instance based on environment configuration."""
    use_local = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"

    if use_local:
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
        llm = ChatOpenAI(
            base_url=ollama_url,
            api_key="ollama",
            model=ollama_model,
            temperature=0,
        )
        logger.info(f"Graph LLM: LOCAL / {ollama_model}")
    else:
        project = os.getenv("GCP_PROJECT_ID", "")
        location = os.getenv("GCP_LOCATION", "us-central1")
        llm = ChatVertexAI(
            model="gemini-2.5-flash",
            project=project,
            location=location,
            temperature=0,
        )
        logger.info(f"Graph LLM: VERTEX AI / Gemini 2.5 Flash (project={project})")

    return llm


# Build once at module level — reused by all nodes
llm = build_llm()
