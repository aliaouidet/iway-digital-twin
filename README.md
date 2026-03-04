# 🏥 I-Way Digital Twin

> **Simulator for an Insurance Backend** — A FastAPI-powered digital twin that mimics the I-Way insurance platform, providing realistic API responses for Adherent (member) and Prestataire (healthcare provider) personas.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

- **Persona-based simulation** — Switch between Adherent (Nadia) and Prestataire (Dr. Amine) via a single header
- **In-memory mock database** — Pre-loaded with realistic insurance data (dossiers, beneficiaries, prestations, remboursements)
- **Knowledge base endpoint** — RAG-ready knowledge base with business rules for vector indexing
- **Claims management** — Create and track support tickets (réclamations)
- **Human escalation** — Simulate escalation to a live agent with queue info
- **RSA key generation** — Auto-generated 2048-bit key pair on startup
- **Latency simulation** — Toggle via environment variable to test slow-network scenarios
- **Full test suite** — 15+ async tests with `pytest` + `httpx`

## 🛠️ Tech Stack

| Component      | Technology                     |
| -------------- | ------------------------------ |
| Framework      | FastAPI                        |
| Server         | Uvicorn                        |
| Validation     | Pydantic v2                    |
| Crypto         | `cryptography` (RSA 2048-bit)  |
| Testing        | pytest + httpx (async)         |
| Config         | python-dotenv                  |

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/aliaouidet/iway-digital-twin.git
cd iway-digital-twin
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 5. Run the server

```bash
python main.py
```

The API will be live at **http://localhost:8000** with interactive docs at **http://localhost:8000/docs**.

## 📡 API Endpoints

| Method | Endpoint                         | Description                          | Tag         |
| ------ | -------------------------------- | ------------------------------------ | ----------- |
| GET    | `/`                              | System status & available personas   | System      |
| GET    | `/api/v1/me`                     | Current user profile                 | Auth        |
| GET    | `/api/v1/knowledge-base`         | Knowledge base for RAG indexing      | RAG Source  |
| GET    | `/api/v1/adherent/dossiers`      | Medical/admin dossiers               | Métier      |
| GET    | `/api/v1/adherent/beneficiaires` | Covered family members               | Métier      |
| GET    | `/api/v1/prestations`            | Medical acts history                 | Métier      |
| GET    | `/api/v1/remboursements`         | Reimbursement history                | Métier      |
| GET    | `/api/v1/reclamations`           | Support ticket history               | Support     |
| POST   | `/api/v1/reclamations`           | Create a new support ticket          | Support     |
| POST   | `/api/v1/support/escalade`       | Escalate to human agent              | Support     |

## 👤 Available Personas

Switch personas using the `X-User-Id` header:

| Header Value   | Role         | Description                           |
| -------------- | ------------ | ------------------------------------- |
| `NADIA_2024`   | Adherent     | Insurance member with full data       |
| `DOC_AMINE`    | Prestataire  | Healthcare provider (Cardiologie)     |

```bash
# As Nadia (default — no header needed)
curl http://localhost:8000/api/v1/me

# As Dr. Amine
curl -H "X-User-Id: DOC_AMINE" http://localhost:8000/api/v1/me
```

## 🧪 Running Tests

```bash
pip install pytest httpx anyio
pytest test_main.py -v
```

## ⚙️ Environment Variables

| Variable           | Default       | Description                              |
| ------------------ | ------------- | ---------------------------------------- |
| `APP_ENV`          | `development` | Application environment                  |
| `APP_NAME`         | —             | Application display name                 |
| `API_VERSION`      | `v1`          | API version prefix                       |
| `SECRET_KEY`       | —             | Secret for simulated token generation    |
| `SIMULATE_LATENCY` | `false`       | Toggle network latency simulation        |

