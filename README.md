# Enterprise Knowledge Copilot

> A production-grade, multi-tenant AI chat application that lets users upload documents and get **citation-grounded answers** from a local LLM — with full data isolation between users.

![Python](https://img.shields.io/badge/Python-3.10-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black)
![MongoDB](https://img.shields.io/badge/MongoDB-7-47A248?style=flat&logo=mongodb&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_DB-FF6B35?style=flat)
![Ollama](https://img.shields.io/badge/Ollama-Llama_3.2-black?style=flat)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white)

---

## What Is This?

This is a **multi-tenant Retrieval-Augmented Generation (RAG)** platform — think ChatGPT, but with two key differences:

1. **Grounded answers:** Upload your own PDF, DOCX, or lecture transcripts and the AI answers *exclusively* from your documents, with citations like `[Lecture 11 at 03:15]`.
2. **Full data isolation:** Every user's documents and conversations are completely separate. User A can never access User B's data — enforced at both the API and vector database layer.

**Normal Chat** mode also works — just open-ended AI conversation with no documents needed.

---

## Features

| Feature | Details |
|---|---|
| 🔐 **Auth** | JWT-based signup/login, bcrypt-hashed passwords |
| 🏢 **Multi-tenancy** | Per-user workspace isolation in MongoDB + ChromaDB |
| 📄 **Document Ingestion** | PDF, DOCX, TXT upload with automatic chunking & embedding |
| 🎬 **Transcript Upload** | JSON lecture transcripts with timestamps → cited answers |
| 🔍 **RAG Pipeline** | BGE-M3 embeddings → cosine similarity search → Llama 3.2 generation |
| 💬 **Streaming Chat** | Server-Sent Events (SSE) for real-time token-by-token streaming |
| ✨ **Suggested Questions** | LLM generates 3 clickable question chips when opening a workspace |
| 🌐 **Public Workspaces** | Owner can share a workspace — visible to every logged-in user |
| 🛡️ **Rate Limiting** | 5 req/min on auth, 15 req/min on chat, 10 req/min on uploads |
| 📦 **File Size Limits** | 5 MB max per upload to protect server resources |
| 🗑️ **Delete Threads** | Threads + all messages deleted atomically |
| 🐳 **Docker** | Full `docker-compose up --build` — no manual setup needed |
| ✅ **26 Tests** | Pytest suite covering auth, CRUD, and cross-user isolation |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser                             │
│              React + Vite (port 5173)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │  HTTP / SSE
┌─────────────────────▼───────────────────────────────────────┐
│              FastAPI Backend (port 8000)                     │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Auth      │  │  Ingestion   │  │   Chat / RAG      │  │
│  │  (JWT +     │  │  (chunk +    │  │  (retrieve +      │  │
│  │  bcrypt)    │  │  embed docs) │  │  generate + SSE)  │  │
│  └─────────────┘  └──────┬───────┘  └────────┬──────────┘  │
└────────────────────────  │  ─────────────────│─────────────┘
                           │                   │
              ┌────────────▼──────┐   ┌────────▼──────────┐
              │   ChromaDB        │   │   Ollama           │
              │   (Vector Store)  │   │   Llama 3.2 (LLM)  │
              │   BGE-M3 embeds   │   │   BGE-M3 (embed)   │
              └───────────────────┘   └────────────────────┘
                           │
              ┌────────────▼──────────┐
              │   MongoDB             │
              │   users / workspaces  │
              │   threads / messages  │
              │   documents metadata  │
              └───────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Backend** | FastAPI (Python 3.10) | Async, fast, excellent OpenAPI docs |
| **Frontend** | React 18 + Vite | Fast HMR, component model |
| **Database** | MongoDB (Motor async driver) | Flexible schema for chat/workspace data |
| **Vector DB** | ChromaDB | Local persistent vector store |
| **Embeddings** | BGE-M3 via Ollama | High-quality multilingual embeddings, runs locally |
| **LLM Provider** | Groq LPU (cloud) / Ollama (local) | Blazing-fast cloud inference or 100% offline local privacy |
| **Auth** | JWT + bcrypt (passlib) | Industry-standard, stateless |
| **Rate Limiting** | SlowAPI | Protects endpoints from abuse |
| **Containerization** | Docker Compose | One-command full-stack startup |
| **Testing** | Pytest + pytest-asyncio | 26 automated tests |

---

## Quick Start

### Option 1 — Docker (Recommended)

> Requires Docker Desktop installed and running.

```bash
git clone https://github.com/YOUR_USERNAME/enterprise-knowledge-copilot.git
cd enterprise-knowledge-copilot

# Copy environment file
cp .env.example .env

# Start everything (backend + frontend + MongoDB + Ollama)
docker-compose up --build
```

Then open **http://localhost:5173** in your browser.

> **First run:** Ollama needs to pull the models. Run these once after the containers start:
> ```bash
> docker exec -it enterprise-copilot-ollama-1 ollama pull llama3.2:3b
> docker exec -it enterprise-copilot-ollama-1 ollama pull bge-m3:latest
> ```

---

### Option 2 — Manual (Local Development)

**Prerequisites:** Python 3.10+, Node 20+, MongoDB running locally, Ollama installed

**1. Clone & set up backend**
```bash
git clone https://github.com/YOUR_USERNAME/enterprise-knowledge-copilot.git
cd enterprise-knowledge-copilot/backend

pip install -r requirements.txt
cp .env.example .env   # edit MONGO_URI and SECRET_KEY

python -m uvicorn main:app --reload
# Backend runs at http://localhost:8000
```

**2. Pull models** (one-time)
```bash
ollama pull llama3.2:3b
ollama pull bge-m3:latest
```

**3. Set up frontend**
```bash
cd ../frontend
npm install
npm run dev
# Frontend runs at http://localhost:5173
```

---

## Environment Variables

Create a `.env` file in the project root (see `.env.example`):

```env
SECRET_KEY=your-super-secret-jwt-key-here
MONGO_URI=mongodb://localhost:27017
DB_NAME=enterprise_copilot_db
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# Dual LLM Support
LLM_PROVIDER=groq        # "groq" for blazing-fast cloud inference, or "ollama" for local
GROQ_API_KEY=gsk_...     # required if LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b
```

---

## How the RAG Pipeline Works

```
User uploads PDF
      │
      ▼
Extract text (pypdf / python-docx)
      │
      ▼
Split into ~1000-char chunks (150-char overlap)
      │
      ▼
Embed with BGE-M3 via Ollama → store in ChromaDB
      │
User asks a question
      │
      ▼
Embed question → cosine similarity search in ChromaDB
(filtered by workspace_id — strict tenant isolation)
      │
      ▼
Top-4 relevant chunks retrieved
      │
      ▼
Llama 3.2 generates answer citing sources
      │
      ▼
SSE stream → tokens appear in real time in the browser
```

**Multi-turn condensation:** If a follow-up question uses pronouns ("what about *it*?"), the system rewrites it into a self-contained search query before hitting the vector DB.

---

## Running Tests

```bash
cd backend
pytest          # run all 26 tests
pytest -v       # verbose output
pytest tests/test_auth.py   # single file
```

**What's covered:**
- Signup, duplicate-email rejection, login, wrong-password rejection, JWT validation
- Workspace creation and per-user listing
- Thread creation (normal + workspace-scoped)
- Message creation, listing, thread-ownership enforcement
- **Cross-user isolation** — the core security guarantee of the system

---

## API Reference

The FastAPI backend auto-generates interactive docs:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/signup` | Register a new user |
| `POST` | `/api/auth/login` | Login, get JWT token |
| `GET` | `/api/workspaces` | List owned + public workspaces |
| `POST` | `/api/workspaces` | Create a workspace |
| `POST` | `/api/workspaces/{id}/documents/upload` | Upload PDF/DOCX/TXT |
| `POST` | `/api/workspaces/{id}/documents/upload-transcript` | Upload timestamped JSON transcript |
| `GET` | `/api/workspaces/{id}/suggested-questions` | AI-generated question chips |
| `POST` | `/api/chat/stream` | SSE streaming chat |
| `POST` | `/api/threads` | Create a thread |
| `DELETE` | `/api/threads/{id}` | Delete thread + messages |

---

## Project Structure

```
enterprise-knowledge-copilot/
├── backend/
│   ├── main.py          # FastAPI app, auth & workspace routes
│   ├── chat.py          # RAG pipeline + SSE streaming
│   ├── ingestion.py     # Document upload, chunking, embedding
│   ├── auth.py          # JWT creation & verification
│   ├── database.py      # MongoDB connection (Motor)
│   ├── models.py        # Pydantic request schemas
│   ├── limiter.py       # SlowAPI rate limiter instance
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/           # 26 pytest tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Root component, state management
│   │   ├── api.js               # All API calls in one place
│   │   ├── components/
│   │   │   ├── ChatWindow.jsx   # Chat UI, SSE streaming, uploads
│   │   │   ├── Sidebar.jsx      # Nav, workspaces, threads
│   │   │   ├── WelcomeScreen.jsx
│   │   │   └── Modal.jsx        # Reusable input modal
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   └── Signup.jsx
│   │   └── styles.css
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Known Limitations & Roadmap

- [x] Cloud deployment configuration ready (Render / Railway + Vercel + MongoDB Atlas + Groq — see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md))
- [ ] Live deployment URL on resume
- [ ] Refresh tokens (currently JWTs expire without silent renewal)
- [ ] Export chat to PDF/Markdown
- [ ] Agentic RAG — LLM decides *whether* to search (LangGraph)
- [ ] Integration tests for full RAG pipeline (requires live Ollama)

---

## Author

Built as a final-year engineering project demonstrating full-stack AI application development with a focus on production-grade concerns: security, multi-tenancy, streaming, containerization, and testability.
