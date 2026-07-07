# Orchestrator — Development Plan

## Status

| Phase | Items | Status |
|-------|-------|--------|
| Phase 1 — UI Polish | 10/10 | ✅ COMPLETED |
| Phase 2 — Production Hardening | 2/3 | 🔄 IN PROGRESS |
| Phase 3 — Advanced Features | 0/3 | 📋 PLANNED |
| Phase 4 — Quality & DevOps | 0/4 | 📋 PLANNED |

---

## Phase 1 — UI Polish ✅

- [x] Copy Code Button (SVG clipboard icon, invisible by default, hover fade)
- [x] Dark/Light Theme Toggle (localStorage persistence, prefers-color-scheme)
- [x] Shift+Enter for newlines, Enter to send
- [x] Fix `:deep()` → `::ng-deep`
- [x] Fix stale tests (`app.component.spec.ts`)
- [x] Handle WS `error` type in frontend switch
- [x] Update `<title>` to "Prompt-to-Agent Orchestrator"
- [x] CSS variables for all colors (dark/light themes)
- [x] Full markdown parser (h1-h5, hr, lists, blockquotes, bold, italic, links)
- [x] Fix Angular view encapsulation (innerHTML styles → global CSS)

---

## Phase 2 — Production Hardening

### 2.1 Persistent Checkpointing (SQLiteSaver)
- [x] Add `langgraph-checkpoint-sqlite` + `aiosqlite` to `requirements.txt`
- [x] Replace `MemorySaver()` with `AsyncSqliteSaver` in `app/agent/graph.py`
- [x] Initialize checkpointer on FastAPI startup, close on shutdown in `app/main.py`
- [x] Add `thread_id` to frontend for resuming conversations
- [x] Persist thread history across server restarts
- [x] Add sidebar with past thread history
- [x] Add thread_id badge with copy button
- [x] Add "New Thread" button to reset state

**Files:** `requirements.txt`, `app/agent/graph.py`, `app/main.py`

### 2.2 Token Cost Dashboard
- [x] Create `TokenTrackingCallback` (LangChain callback) in `app/agent/callbacks.py`
- [x] Capture `prompt_tokens`, `completion_tokens`, `total_tokens` per LLM call
- [x] Calculate cost using Mistral pricing (input: $0.27/1M, output: $0.81/1M)
- [ ] Store per-thread stats in SQLite
- [x] Send `token_usage` WebSocket message after each response
- [x] Add token stats display in frontend (footer badge or stats panel)
- [ ] Add `GET /api/v1/stats/{thread_id}` REST endpoint

**New file:** `app/agent/callbacks.py`
**Modified:** `app/main.py`, `frontend/src/app/app.component.ts`, `frontend/src/app/app.component.html`

**WebSocket message:**
```json
{
  "type": "token_usage",
  "prompt_tokens": 150,
  "completion_tokens": 320,
  "total_tokens": 470,
  "estimated_cost": 0.0003
}
```

### 2.3 Agent Self-Reflection Loop
- [ ] Add `reflect` node to LangGraph in `app/agent/graph.py`
- [ ] Use lightweight model (mistral-small) for reflection evaluation
- [ ] Quality score (1-10) — if < 7, route back to agent for retry
- [ ] Cap retries at 2 to prevent infinite loops
- [ ] Send `reflection` WebSocket message with score + reasoning
- [ ] Frontend shows reflection as collapsible section in activity log

**Graph change:**
```
Before:  agent → tools → agent → done
After:   agent → tools → agent → reflect → (score < 7) → agent | (score >= 7) → done
```

**Files:** `app/agent/graph.py`, `app/main.py`, `frontend/src/app/app.component.ts`

### Execution Order
1. 2.1 Checkpointing (foundation)
2. 2.2 Token Dashboard (needs callback infra)
3. 2.3 Self-Reflection (builds on both)

---

## Phase 3 — Advanced Features

### 3.1 Execution History
- [ ] List all past threads with timestamps in sidebar
- [ ] Load and resume old conversations
- [ ] Search across thread history

**Depends on:** 2.1 (SQLiteSaver)

### 3.2 File Upload Support
- [ ] Drag-and-drop zone in frontend
- [ ] Upload files to `workspace/` directory
- [ ] Agent reads uploaded files as context
- [ ] Preview uploaded files in file preview section

### 3.3 Time-Travel Debugging
- [ ] Visualize LangGraph state at each step
- [ ] Allow user to replay from any checkpoint
- [ ] Show branching paths when agent retried

**Depends on:** 2.1 (SQLiteSaver), 3.1 (Execution History)

---

## Phase 4 — Quality & DevOps

### 4.1 Parallel Tool Execution
- [ ] Enable parallel tool calls in LangGraph agent
- [ ] Merge results from parallel executions
- [ ] Frontend shows parallel tool progress

### 4.2 A/B Testing
- [ ] Route same prompt to different models/configs
- [ ] Compare output quality side-by-side
- [ ] Track which config performs better

### 4.3 pytest Tests
- [ ] Unit tests for `tools.py` (search, E2B, file I/O, RAG, SQL)
- [ ] Unit tests for `graph.py` (agent flow, HITL interrupts)
- [ ] Unit tests for `main.py` (WebSocket, REST endpoints)
- [ ] Integration tests for full agent workflow
- [ ] Target: 80%+ coverage

### 4.4 CI/CD Pipeline
- [ ] GitHub Actions: lint → test → build → deploy
- [ ] Docker image build on push to main
- [ ] Auto-deploy to Render on merge
- [ ] Test gate: block merge if tests fail

---

## Decisions (Locked In)

1. **Reflection model:** mistral-large-latest (same as main agent)
2. **Token dashboard scope:** Both per-thread stats + global `/api/v1/stats` endpoint
3. **Reflection visibility:** Real-time WebSocket stream
4. **Thread history:** Sidebar with past threads in the UI
