# I-Way Digital Twin

> **Hybrid AI Chatbot & Agent Platform** for I-Way Solutions (I-Sante project) — a mock-first health insurance backend with AI-powered conversational assistant, semantic RAG search, and a Streamlit chat interface.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent-orange)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

This project implements a **mock-first** approach to building an AI-powered insurance assistant. Since the real Java Spring Boot backend is in development, this platform provides:

1. **Mock API Server** — FastAPI server with RS256 JWT auth, simulating the full I-Way insurance backend
2. **AI Agent** — LangGraph stateful agent powered by Gemini 2.5 Flash (or local Ollama), with tool-calling capabilities
3. **RAG Engine** — FAISS vector store with sentence-transformers for semantic search over insurance rules
4. **Chat UI** — Streamlit-based conversational interface for testing the AI assistant

## Architecture

```
                        +------------------+
                        |   Streamlit UI   |   (chat_ui.py)
                        +--------+---------+
                                 |
                        +--------+---------+
                        |  LangGraph Agent |   (agent.py)
                        +--------+---------+
                                 |
               +-----------------+-----------------+
               |                 |                 |
      +--------+------+  +------+-------+  +------+--------+
      | API Tool      |  | RAG Tool     |  | Escalation    |
      | (dossiers)    |  | (FAISS)      |  | Tool          |
      +--------+------+  +------+-------+  +------+--------+
               |                 |                 |
      +--------+-----------------+-----------------+--------+
      |              Mock API Server (FastAPI)               |
      |                    main.py                           |
      +-----------------------------------------------------+
```

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Authentication | RS256 JWT (PyJWT + cryptography) |
| AI Orchestration | LangGraph, LangChain |
| LLM (Cloud) | Gemini 2.5 Flash via langchain-google-genai |
| LLM (Local) | Qwen 3.5 9B via Ollama + langchain-openai |
| Vector Search | FAISS + sentence-transformers (all-MiniLM-L6-v2) |
| Chat Interface | Streamlit |
| Testing | pytest + httpx (async) |
| Config | python-dotenv |

## Quick Start

### 1. Clone and setup

```bash
git clone https://github.com/aliaouidet/iway-digital-twin.git
cd iway-digital-twin
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your `GOOGLE_API_KEY` (get one at [Google AI Studio](https://aistudio.google.com/apikey)):

```env
GOOGLE_API_KEY=your_actual_api_key_here
```

### 3. Run the Mock Server

```bash
python main.py
```

The API will be live at **http://localhost:8000** with interactive docs at **http://localhost:8000/docs**.

### 4. Run the Chat UI

In a second terminal:

```bash
streamlit run chat_ui.py
```

Open **http://localhost:8501**, log in as Nadia or Dr. Amine, and start chatting.

### 5. Run the Agent (CLI)

Alternatively, test the agent in the terminal:

```bash
python agent.py
```

## Project Structure

```
iway-digital-twin/
├── main.py              # FastAPI mock server (JWT auth, 12 endpoints, mock DB)
├── agent.py             # LangGraph stateful agent (Gemini/Ollama toggle)
├── bot_tools.py         # LangChain tools (API calls, RAG search, escalation)
├── rag_engine.py        # FAISS vector store + sentence-transformers
├── chat_ui.py           # Streamlit chat interface
├── test_main.py         # 22 tests for the mock server
├── test_bot_tools.py    # 24 tests for tools, agent, and integration
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .gitignore           # Git ignore rules
└── LICENSE              # MIT License
```

## API Endpoints

All `/api/v1/*` endpoints require a valid JWT Bearer token obtained from `/auth/login`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | System status and available personas |
| POST | `/auth/login` | Authenticate and receive JWT token |
| GET | `/auth/public-key` | RSA public key (PEM format) |
| GET | `/api/v1/me` | Current user profile |
| GET | `/api/v1/knowledge-base` | Knowledge base entries (12 items) |
| GET | `/api/v1/adherent/dossiers` | Medical/admin dossiers |
| GET | `/api/v1/adherent/beneficiaires` | Covered family members |
| GET | `/api/v1/prestations` | Medical acts history |
| GET | `/api/v1/remboursements` | Reimbursement history |
| GET | `/api/v1/reclamations` | Support ticket history |
| POST | `/api/v1/reclamations` | Create a new support ticket |
| POST | `/api/v1/support/escalade` | Escalate to human agent |
| GET | `/api/v1/dashboard/tickets` | Escalation tickets (dashboard) |

## Test Personas

| Profile | Matricule | Password | Role |
|---|---|---|---|
| Nadia Mansour | `12345` | `pass` | Adherent (insurance member) |
| Dr. Amine Zaid | `99999` | `med` | Prestataire (healthcare provider) |

```bash
# Example: login as Nadia
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"matricule": "12345", "password": "pass"}'
```

## AI Agent

The LangGraph agent (`agent.py`) orchestrates three tools:

| Tool | Purpose | Mechanism |
|---|---|---|
| `get_personal_dossiers` | Fetch user's medical files | `GET /api/v1/adherent/dossiers` with Bearer token |
| `search_knowledge_base` | Insurance rules lookup | FAISS semantic search (12 KB entries) |
| `escalate_to_human` | Transfer to human agent | `POST /api/v1/support/escalade` |

### LLM Toggle

Switch between cloud and local LLM via environment variable:

```env
# Cloud (default) — requires GOOGLE_API_KEY
USE_LOCAL_LLM=false

# Local — requires Ollama running with qwen3.5:9b
USE_LOCAL_LLM=true
```

For local mode, install and run [Ollama](https://ollama.com):

```bash
ollama pull qwen3.5:9b
ollama serve
```

## RAG Engine

The knowledge base uses **FAISS** with **sentence-transformers** (all-MiniLM-L6-v2) for semantic vector search. The system indexes 12 insurance policy entries covering:

- Dental coverage and ceilings
- Birth premium
- Reimbursement timelines
- Hospitalization coverage
- Optical care
- Pharmacy and medications
- Chronic illness protocols
- Maternity leave
- Emergency procedures
- Provider conventions

The RAG architecture is designed for incremental upgrades:

| Level | Implementation | Status |
|---|---|---|
| Level 2 | FAISS + sentence-transformers | Current |
| Level 3 | + BM25 hybrid search | Ready to add |
| Level 4 | ChromaDB + PDF loader + reranker | Planned |

## Running Tests

```bash
# Run all tests (46 total)
pytest test_main.py test_bot_tools.py -v

# Run only server tests (22)
pytest test_main.py -v

# Run only AI/tool tests (24)
pytest test_bot_tools.py -v
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `USE_LOCAL_LLM` | `false` | Toggle between Cloud (Gemini) and Local (Ollama) |
| `GOOGLE_API_KEY` | — | Google AI API key (required for cloud mode) |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama server URL (local mode) |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama model name (local mode) |
| `MOCK_SERVER_URL` | `http://localhost:8000` | Mock server base URL |

## License

[MIT](LICENSE)
