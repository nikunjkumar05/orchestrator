# 🚀 Prompt-to-Agent Orchestrator

A zero-config, production-ready AI agent pipeline that converts a single natural language prompt into a fully executed multi-step workflow. Built with **LangGraph**, **FastAPI**, **Angular**, and **Docker**, it leverages ReAct-style planning to coordinate tools across web search, code execution, database operations, and file system tasks.

App Link: https://prompt-to-agent-orchestrator.onrender.com/
---

## 🛠️ Tech Stack

*   **Backend:** Python 3.11, FastAPI, LangGraph, LangChain, SQLAlchemy (SQLite)
*   **Frontend:** Angular (v19), Custom Glassmorphism CSS, RxJS
*   **LLM Engine:** Mistral AI (`mistral-large-latest`)
*   **Infrastructure:** Docker, Docker Compose, Render Blueprints (Infrastructure as Code)

---

## ✨ Features

*   **ReAct-Style Planning Agent:** Uses LangGraph state machines to dynamically decide which tools to call, inspect their outputs, and iteratively arrive at the final answer.
*   **Integrated Multi-Tool Suite:**
    *   🔍 **Web Search:** Custom DuckDuckGo wrapper avoiding LangChain integration issues.
    *   💻 **Code Execution:** Ephemeral python REPL environment.
    *   📁 **File I/O:** Safe workspace directory access for creating, editing, and reading files.
    *   🗄️ **Database Tool:** Persistent SQLite storage integration.
*   **Beautiful UI:** Custom built Angular frontend featuring dark mode, glassmorphism design tokens, smooth animations, and structured displays for intermediate agent thought logs.
*   **Single-Container Deployment:** Uses a multi-stage `Dockerfile` to build the Angular frontend and serve it statically via FastAPI.

---

## 📂 Project Structure

```
├── app/                        # FastAPI Backend
│   ├── agent/                  
│   │   ├── graph.py            # LangGraph agent state machine definitions
│   │   └── tools.py            # Custom tool implementations (Search, DB, REPL, File)
│   ├── main.py                 # FastAPI application routes (static serving & CORS)
│   └── models.py               # Pydantic data schemas
├── frontend/                   # Angular Frontend App
│   ├── src/                    
│   │   ├── app/                # UI Components & services
│   │   └── styles.css          # Global glassmorphism theme styling
│   └── package.json            
├── Dockerfile                  # Multi-stage container build definition
├── docker-compose.yml          # Local container configuration
├── render.yaml                 # Render Blueprint for zero-config cloud deploy
└── requirements.txt            # Python dependencies
```

---

## 🚀 Getting Started

### Prerequisites

Ensure you have the following installed locally:
*   [Docker & Docker Compose](https://www.docker.com/)
*   A **Mistral AI API Key** (Get one at [Mistral Console](https://console.mistral.ai/))

### Configuration

Create a `.env` file in the root directory (already added to `.gitignore`):

```env
MISTRAL_API_KEY=your_mistral_api_key_here
MISTRAL_MODEL=mistral-large-latest
```

### Local Deployment (Docker)

To build and launch the application (both frontend and backend) in a single step:

```bash
# Build the container (this compiles the Angular app)
docker-compose build --no-cache

# Run the container
docker-compose up
```

Once running, access the application in your browser:
👉 **`http://localhost:8000`**

---

## ☁️ Cloud Deployment (Render)

This repository includes a `render.yaml` Blueprint to support instant deployment to Render.

1.  Push this codebase to a personal GitHub or GitLab repository.
2.  Go to [Render Dashboard](https://render.com/) -> **Blueprints** -> **New Blueprint Instance**.
3.  Select your repository.
4.  Render will prompt you for the `MISTRAL_API_KEY` environment variable. Paste it in.
5.  Click **Apply**. Render will build the Angular UI and serve it over a secure HTTPS URL automatically!

---

## 🔌 API Endpoints

If you wish to interact with the backend programmatically:

*   `POST /api/v1/execute` - Send a prompt to the agent pipeline.
    *   **Body:** `{"prompt": "Your instruction here"}`
    *   **Returns:** JSON containing the final answer and a step-by-step trace of intermediate messages.
*   `GET /health` - Health check endpoint returning `{"status": "healthy"}`.

### Example API Request (PowerShell)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/execute" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"prompt": "Search the web for the current price of Bitcoin."}'
```
