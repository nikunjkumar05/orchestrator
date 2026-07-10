# Orchestrator — Novelty Implementation Plan

## Overview

Six genuinely novel features to differentiate this orchestrator from standard LangGraph agent pipelines.

---

## Status

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Self-Evolving Tool Creation | ⬜ PLANNED |
| Phase 2 | Cross-Thread Memory with Forgetting Curve | ⬜ PLANNED |
| Phase 3 | Uncertainty-Driven Human Escalation | ⬜ PLANNED |
| Phase 4 | Contrastive Reflection | ⬜ PLANNED |
| Phase 5 | Parallel Branching with Merge | ⬜ PLANNED |
| Phase 6 | Tool Composition Chains | ⬜ PLANNED |

---

## Phase 1: Self-Evolving Tool Creation

**Goal:** Agent can dynamically create, test, and register new tools at runtime.

### Concept

When the agent detects a repeated task pattern (e.g., "always parse CSVs this way"), it:
1. Generates a new `@tool` function as a Python string
2. Tests it in the E2B sandbox to verify it works
3. Saves it to `workspace/tools/` as a `.py` file
4. Loads it on next startup and adds it to `all_tools`

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS evolved_tools (
    tool_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    code TEXT NOT NULL,
    source_prompt TEXT,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    is_active INTEGER DEFAULT 1
);
```

### Files to Create

| File | Purpose |
|------|---------|
| `app/agent/tool_evolver.py` | Core logic: generate, test, register evolved tools |
| `workspace/tools/` | Directory for persisted tool `.py` files |

### Files to Modify

| File | Changes |
|------|---------|
| `app/agent/tools.py` | Add `create_tool` meta-tool that agent calls to evolve new tools; add `list_tools` tool to see available tools; add `evolve_tool` tool to trigger creation |
| `app/agent/graph.py` | Load evolved tools on startup; add them to `all_tools` |
| `app/main.py` | Initialize `workspace/tools/` dir on startup; add `GET /api/v1/tools` endpoint |
| `app/models.py` | Add `ToolInfo` response model |

### Tool Definitions

```python
@tool
def create_tool(name: str, description: str, code: str) -> str:
    """Create a new tool from Python code. The code must define a function
    decorated with @tool from langchain_core.tools.
    
    Args:
        name: Tool name (snake_case, unique)
        description: What the tool does (used by agent to decide when to call it)
        code: Full Python code including imports and @tool decorator
    """
    # 1. Validate code syntax via ast.parse()
    # 2. Test in E2B sandbox with a test call
    # 3. Save to workspace/tools/{name}.py
    # 4. Register in evolved_tools table
    # 5. Return success/failure

@tool
def list_tools() -> str:
    """List all available tools including evolved tools."""
    # Returns names and descriptions of all tools

@tool
def delete_tool(name: str) -> str:
    """Deactivate an evolved tool."""
    # Sets is_active = 0 in DB, removes from runtime
```

### Tool Evolver Logic (`tool_evolver.py`)

```python
class ToolEvolver:
    def __init__(self, workspace_dir: str, db_conn):
        self.workspace_dir = workspace_dir
        self.db_conn = db_conn
        self.tools_dir = os.path.join(workspace_dir, "tools")
        os.makedirs(self.tools_dir, exist_ok=True)
    
    async def create_tool(self, name, description, code, llm) -> dict:
        """1. Validate syntax, 2. Test in sandbox, 3. Save, 4. Register"""
        # Step 1: ast.parse(code) — check syntax
        # Step 2: Use E2B to run a test invocation
        # Step 3: Write to workspace/tools/{name}.py
        # Step 4: INSERT INTO evolved_tools
        # Step 5: Return tool object for runtime loading
    
    async def load_tools(self) -> list:
        """Load all active evolved tools from DB on startup"""
        # SELECT * FROM evolved_tools WHERE is_active = 1
        # For each: exec(code) to get tool object
        # Return list of tool objects
    
    async def record_usage(self, name: str, success: bool):
        """Track tool success/failure for quality"""
        if success:
            UPDATE success_count += 1, last_used_at = now
        else:
            UPDATE failure_count += 1
    
    async def get_tool_stats(self) -> list:
        """Return stats for all evolved tools"""
```

### Agent Prompt Addition

Add to system message:
```
You have a meta-tool called `create_tool`. When you notice yourself
performing the same multi-step operation repeatedly, consider creating
a new tool to automate it. The tool must be self-contained Python code
with the @tool decorator.
```

### Graph Changes

```python
# In graph.py — load evolved tools on startup
async def init_checkpointer():
    # ... existing code ...
    evolved = await tool_evolver.load_tools()
    all_tools.extend(evolved)
```

### API Endpoints

```
GET  /api/v1/tools              — List all tools (static + evolved)
POST /api/v1/tools/test         — Test code in sandbox without saving
GET  /api/v1/tools/{name}/stats — Usage stats for evolved tool
```

### Frontend Changes

| File | Changes |
|------|---------|
| `app.component.ts` | Add `tools: ToolInfo[]` array; add `fetchTools()` method |
| `app.component.html` | Add "Tools" section in sidebar showing evolved tools with stats |

### WebSocket Messages

```json
{ "type": "tool_created", "name": "parse_csv", "description": "..." }
{ "type": "tool_test_failed", "name": "parse_csv", "error": "..." }
```

### Execution Order

1. Create `app/agent/tool_evolver.py` with `ToolEvolver` class
2. Create `workspace/tools/` directory
3. Add evolved_tools table creation to `app/main.py` startup
4. Add `create_tool`, `list_tools`, `delete_tool` to `app/agent/tools.py`
5. Modify `graph.py` to load evolved tools on startup
6. Add API endpoints
7. Add frontend display
8. Add agent system prompt guidance

---

## Phase 2: Cross-Thread Memory with Forgetting Curve

**Goal:** Agent learns from past conversations; old patterns fade unless reinforced.

### Concept

1. After each successful conversation, extract "reasoning patterns" (tool sequences, strategies)
2. Store them in a memory table with timestamps
3. Apply exponential decay: strength = e^(-λ * days_since_last_use)
4. Patterns that get reused stay strong; unused ones fade below threshold
5. Inject strong patterns as few-shot examples in system prompt

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS memory_patterns (
    pattern_id TEXT PRIMARY KEY,
    pattern_type TEXT NOT NULL,          -- 'tool_sequence', 'strategy', 'preference'
    description TEXT NOT NULL,           -- human-readable
    tool_sequence TEXT,                  -- JSON array of tool names
    prompt_keywords TEXT,                -- JSON array of trigger keywords
    success_count INTEGER DEFAULT 1,
    failure_count INTEGER DEFAULT 0,
    strength REAL DEFAULT 1.0,           -- 0.0 to 1.0
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    thread_ids TEXT DEFAULT '[]'         -- JSON array of thread_ids that used this
);
```

### Files to Create

| File | Purpose |
|------|---------|
| `app/agent/memory.py` | Core: extract patterns, apply forgetting, query memories |

### Files to Modify

| File | Changes |
|------|---------|
| `app/agent/graph.py` | After completion: extract patterns; before start: query relevant memories; add decay job |
| `app/main.py` | Add memory tables on startup; add `GET /api/v1/memory` endpoint |
| `app/agent/callbacks.py` | Track tool sequence for pattern extraction |

### Memory Manager (`memory.py`)

```python
class MemoryManager:
    LAMBDA = 0.01  # Decay rate — ~70 days half-life
    
    def __init__(self, db_conn):
        self.conn = db_conn
    
    async def extract_patterns(self, messages, thread_id) -> list:
        """Analyze completed conversation for reusable patterns"""
        # Pattern 1: Tool sequences (e.g., search → write_file → e2b_sandbox)
        # Pattern 2: Strategy (e.g., "for data analysis, first search, then code")
        # Pattern 3: User preference (e.g., "always outputs in markdown tables")
        
        # Use LLM to identify patterns:
        # "Analyze this conversation and extract reusable patterns.
        #  For each pattern, return: type, description, tool_sequence, keywords."
    
    async def store_patterns(self, patterns, thread_id):
        """Store new patterns or strengthen existing ones"""
        for p in patterns:
            existing = await self.find_similar(p.description)
            if existing:
                # Strengthen existing pattern
                await self.strengthen(existing.pattern_id, thread_id)
            else:
                # Insert new pattern
                await self.insert_pattern(p, thread_id)
    
    async def apply_forgetting(self):
        """Apply exponential decay to all patterns"""
        # UPDATE strength = strength * exp(-λ * days_since_last_used)
        # DELETE WHERE strength < 0.01  (effectively forgotten)
    
    async def query_relevant(self, prompt: str, limit: int = 5) -> list:
        """Find patterns relevant to current prompt"""
        # 1. Extract keywords from prompt
        # 2. Match against prompt_keywords
        # 3. Filter by strength > 0.3
        # 4. Sort by (strength * relevance_score) DESC
        # 5. Return top `limit` patterns
    
    async def format_as_context(self, patterns: list) -> str:
        """Format patterns for injection into system prompt"""
        # Return:
        # "Relevant past patterns:
        #  - [Tool Sequence] For web research: search → write_file → e2b_sandbox (strength: 0.85)
        #  - [Strategy] When analyzing data, always validate inputs first (strength: 0.72)"
    
    async def record_use(self, pattern_id, thread_id, success):
        """Record that a pattern was used"""
        # Increment success/failure count
        # Update last_used_at
        # Strengthen if success, weaken if failure
    
    async def get_stats(self) -> dict:
        """Return memory stats"""
        # Total patterns, avg strength, forgotten count, active count
```

### Graph Changes

```python
# In graph.py — after agent completes
async def post_completion_extract(state, thread_id):
    """Extract patterns after successful completion"""
    messages = state["messages"]
    patterns = await memory.extract_patterns(messages, thread_id)
    await memory.store_patterns(patterns, thread_id)

# In graph.py — before agent starts
async def pre_start_inject(prompt, config):
    """Inject relevant memories into system prompt"""
    relevant = await memory.query_relevant(prompt)
    if relevant:
        context = await memory.format_as_context(relevant)
        # Prepend to system message
```

### API Endpoints

```
GET  /api/v1/memory              — List all patterns with strength
GET  /api/v1/memory/stats        — Memory statistics
POST /api/v1/memory/decay        — Trigger manual decay (admin)
DELETE /api/v1/memory/{id}       — Manually forget a pattern
```

### WebSocket Messages

```json
{ "type": "memory_loaded", "count": 3, "patterns": [...] }
{ "type": "pattern_extracted", "description": "..." }
```

### Execution Order

1. Create `app/agent/memory.py`
2. Add memory tables to startup in `app/main.py`
3. Modify `app/agent/graph.py` — add pre/post hooks
4. Modify `app/agent/callbacks.py` — track tool sequences
5. Add API endpoints
6. Add frontend memory panel
7. Tune decay rate (λ) based on testing

---

## Phase 3: Uncertainty-Driven Human Escalation

**Goal:** Agent tracks confidence and proactively asks for help when uncertain.

### Concept

After each tool execution, compute a confidence score based on:
- Tool success/failure
- Result relevance (semantic similarity to query)
- Historical tool reliability (from memory_patterns)
- Error presence in output

If confidence < threshold → pause and ask user for guidance
If confidence >= threshold → proceed autonomously

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS tool_reliability (
    tool_name TEXT PRIMARY KEY,
    total_calls INTEGER DEFAULT 0,
    success_calls INTEGER DEFAULT 0,
    avg_response_quality REAL DEFAULT 0.5,  -- 0.0 to 1.0
    last_updated TEXT
);
```

### Files to Create

| File | Purpose |
|------|---------|
| `app/agent/confidence.py` | Confidence scoring logic |

### Files to Modify

| File | Changes |
|------|---------|
| `app/agent/graph.py` | Add confidence check node after tools; conditionally pause |
| `app/agent/tools.py` | Add `get_tool_stats` tool for agent to query its own reliability |
| `app/main.py` | Add confidence tables; add `GET /api/v1/confidence` endpoint |
| `app/agent/callbacks.py` | Track per-tool success/failure |

### Confidence Scorer (`confidence.py`)

```python
class ConfidenceScorer:
    THRESHOLD = 0.6  # Below this → escalate to human
    
    def __init__(self, db_conn):
        self.conn = db_conn
    
    async def score_tool_result(self, tool_name, result, query) -> float:
        """Compute confidence 0.0 to 1.0"""
        factors = []
        
        # Factor 1: Tool success (0.0 or 1.0)
        has_error = "error" in result.lower() or "failed" in result.lower()
        factors.append(0.0 if has_error else 1.0)
        
        # Factor 2: Tool reliability (from historical data)
        reliability = await self.get_tool_reliability(tool_name)
        factors.append(reliability)
        
        # Factor 3: Result relevance (keyword overlap with query)
        relevance = self.keyword_overlap(result, query)
        factors.append(relevance)
        
        # Factor 4: Result length (too short might mean failure)
        length_score = min(len(result) / 200, 1.0)
        factors.append(length_score)
        
        # Weighted average
        weights = [0.3, 0.3, 0.25, 0.15]
        confidence = sum(f * w for f, w in zip(factors, weights))
        return round(confidence, 3)
    
    async def get_tool_reliability(self, tool_name) -> float:
        """Get historical reliability for a tool"""
        # SELECT success_calls / total_calls FROM tool_reliability
        # Default 0.5 if no history
    
    async def update_reliability(self, tool_name, success: bool):
        """Update tool reliability after execution"""
        # Increment counters
        # Recalculate avg_response_quality
    
    def keyword_overlap(self, text: str, query: str) -> float:
        """Simple relevance metric"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())
        if not query_words:
            return 0.5
        overlap = len(query_words & text_words) / len(query_words)
        return min(overlap * 2, 1.0)  # Cap at 1.0
    
    async def should_escalate(self, confidence: float) -> bool:
        """Decide whether to pause for human input"""
        return confidence < self.THRESHOLD
```

### Graph Changes

```python
# Modified graph structure:
# 
#   agent → tools → confidence_check → (low) → escalate_to_human → agent
#                                       (high) → agent

from langgraph.graph import END

def confidence_check(state):
    """Check confidence after tool execution"""
    # Score last tool result
    # If below threshold → route to "escalate" node
    # If above threshold → route to "agent" node

# In graph:
graph.add_node("confidence_check", confidence_check)
graph.add_conditional_edges("confidence_check", route_by_confidence, {
    "escalate": "escalate_to_human",
    "continue": "agent"
})
```

### Escalation Message Template

```python
ESCALATION_TEMPLATE = """
I'm not confident about the result of {tool_name}.

**Confidence score:** {confidence:.0%}
**What happened:** {result_summary}
**What I'm unsure about:** {uncertainty_reason}

Could you help me decide:
1. Should I retry with different parameters?
2. Should I try a different approach?
3. Is the result actually correct and I should continue?

Current context: {query_context}
"""
```

### API Endpoints

```
GET  /api/v1/confidence/stats       — Tool reliability stats
GET  /api/v1/confidence/history     — Escalation history
POST /api/v1/confidence/threshold   — Update threshold (admin)
```

### WebSocket Messages

```json
{ "type": "escalation", "tool": "search_tool", "confidence": 0.35, "reason": "..." }
{ "type": "confidence_update", "tool": "search_tool", "confidence": 0.82 }
```

### Frontend Changes

| File | Changes |
|------|---------|
| `app.component.ts` | Add `escalation: EscalationInfo \| null`; handle `escalation` message type; add response form |
| `app.component.html` | Add escalation card (similar to approval card but with guidance options) |

### Execution Order

1. Create `app/agent/confidence.py`
2. Add tool_reliability table to startup
3. Modify `app/agent/graph.py` — add confidence_check node
4. Modify `app/agent/callbacks.py` — track tool success/failure
5. Modify `app/main.py` — add escalation handling in WebSocket
6. Add frontend escalation UI
7. Tune threshold based on testing

---

## Phase 4: Contrastive Reflection

**Goal:** Reflection step generates "what would have been better" examples, not just scores.

### Concept

After agent completes, a lightweight model evaluates:
1. Quality score (1-10)
2. What went well (positive patterns)
3. What could be better (contrastive examples)
4. Specific "if I had done X instead of Y" examples

These contrastive examples are stored and used as few-shot for future tasks.

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS contrastive_examples (
    example_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    quality_score INTEGER NOT NULL,
    what_went_well TEXT NOT NULL,
    what_could_improve TEXT NOT NULL,
    contrastive_pairs TEXT NOT NULL,  -- JSON: [{"tool_used": "X", "tool_better": "Y", "reason": "Z"}]
    prompt_summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    was_applied INTEGER DEFAULT 0
);
```

### Files to Create

| File | Purpose |
|------|---------|
| `app/agent/contrastive_reflection.py` | Core reflection + contrastive generation |

### Files to Modify

| File | Changes |
|------|---------|
| `app/agent/graph.py` | Add reflect node after agent completion; add contrastive context injection |
| `app/main.py` | Add reflection tables; add `GET /api/v1/reflection` endpoint |
| `app/agent/callbacks.py` | Track tool sequences for contrastive analysis |

### Contrastive Reflector (`contrastive_reflection.py`)

```python
class ContrastiveReflector:
    def __init__(self, llm):
        self.llm = llm  # Lightweight model (mistral-small)
    
    async def reflect(self, messages, prompt) -> dict:
        """Analyze conversation and generate contrastive examples"""
        
        reflection_prompt = f"""
        Analyze this conversation and provide structured feedback.
        
        Original prompt: {prompt}
        Conversation: {format_messages(messages)}
        
        Return JSON:
        {{
            "quality_score": 1-10,
            "what_went_well": ["list of good decisions"],
            "what_could_improve": ["list of improvements"],
            "contrastive_pairs": [
                {{
                    "situation": "when X happened",
                    "tool_used": "what was done",
                    "tool_better": "what would have been better",
                    "reason": "why the alternative is better"
                }}
            ]
        }}
        """
        
        response = await self.llm.ainvoke(reflection_prompt)
        return parse_json(response.content)
    
    async def store_examples(self, reflection: dict, thread_id: str):
        """Store contrastive examples for future use"""
        for pair in reflection["contrastive_pairs"]:
            # Check if similar example exists
            existing = await self.find_similar(pair["situation"])
            if existing:
                # Strengthen existing
                await self.strengthen_example(existing.example_id)
            else:
                # Insert new
                await self.insert_example(pair, thread_id, reflection)
    
    async def query_relevant_examples(self, prompt: str, limit: int = 3) -> list:
        """Find contrastive examples relevant to current prompt"""
        # Match prompt keywords against stored examples
        # Sort by (quality_score * relevance) DESC
        # Return top `limit`
    
    async def format_for_prompt(self, examples: list) -> str:
        """Format contrastive examples as few-shot context"""
        # Return:
        # "Lessons from past experiences:
        #  - When doing web research, use Tavily over DuckDuckGo for better results
        #    (Previously used DuckDuckGo, got incomplete data)
        #  - For data analysis, validate CSV structure before processing
        #    (Previously assumed valid format, got errors)"
```

### Graph Changes

```python
# Modified graph structure:
#
#   agent → tools → agent → reflect → (score < 7) → agent (retry) → done
#                                 → (score >= 7) → done

async def reflect_node(state):
    """Reflect on conversation quality"""
    messages = state["messages"]
    prompt = extract_original_prompt(messages)
    reflection = await reflector.reflect(messages, prompt)
    await reflector.store_examples(reflection, state["thread_id"])
    return {"reflection": reflection}

# Conditional edge after reflect
def should_retry(state):
    score = state.get("reflection", {}).get("quality_score", 10)
    return "retry" if score < 7 else "done"
```

### API Endpoints

```
GET  /api/v1/reflection/examples           — List all contrastive examples
GET  /api/v1/reflection/examples/relevant  — Query relevant to prompt
GET  /api/v1/reflection/stats              — Reflection statistics
DELETE /api/v1/reflection/examples/{id}    — Remove an example
```

### WebSocket Messages

```json
{
    "type": "reflection",
    "quality_score": 8,
    "what_went_well": ["Used search effectively", "Clean code output"],
    "what_could_improve": ["Could have validated input first"],
    "contrastive_pairs": [...]
}
```

### Frontend Changes

| File | Changes |
|------|---------|
| `app.component.ts` | Add `reflection: ReflectionInfo \| null`; handle `reflection` message; add collapsible section |
| `app.component.html` | Add collapsible "Reflection" section in activity log showing score + contrastive pairs |

### Execution Order

1. Create `app/agent/contrastive_reflection.py`
2. Add contrastive_examples table to startup
3. Modify `app/agent/graph.py` — add reflect node
4. Add context injection before agent starts
5. Add API endpoints
6. Add frontend reflection display
7. Test retry loop (max 2 retries to prevent infinite loops)

---

## Phase 5: Parallel Branching with Merge

**Goal:** Agent can spawn parallel sub-tasks and merge results.

### Concept

Instead of linear ReAct, agent can:
1. Detect when a prompt requires multiple independent research paths
2. Spawn parallel sub-agents (each with own thread)
3. Each sub-agent works independently
4. Results merge back into main conversation

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS parallel_branches (
    branch_id TEXT PRIMARY KEY,
    parent_thread_id TEXT NOT NULL,
    child_thread_id TEXT NOT NULL,
    task_description TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, running, completed, failed
    result TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
```

### Files to Create

| File | Purpose |
|------|---------|
| `app/agent/parallel.py` | Branch spawning, merging, and coordination |

### Files to Modify

| File | Changes |
|------|---------|
| `app/agent/tools.py` | Add `spawn_branch` and `merge_results` tools |
| `app/agent/graph.py` | Handle branch detection and parallel execution |
| `app/main.py` | Add parallel branch tables; manage multiple WebSocket streams |
| `app/models.py` | Add `BranchInfo`, `MergeResult` models |

### Parallel Manager (`parallel.py`)

```python
class ParallelManager:
    def __init__(self, agent_executor, db_conn):
        self.agent = agent_executor
        self.conn = db_conn
    
    async def detect_parallel_opportunity(self, prompt: str, llm) -> bool:
        """Use LLM to detect if prompt benefits from parallel execution"""
        detection_prompt = f"""
        Can this task be broken into independent sub-tasks that can run in parallel?
        Answer YES or NO and list the sub-tasks if yes.
        
        Task: {prompt}
        """
        response = await llm.ainvoke(detection_prompt)
        return parse_parallel_response(response.content)
    
    async def spawn_branches(self, parent_thread_id: str, tasks: list) -> list:
        """Spawn parallel sub-agents"""
        branches = []
        for task in tasks:
            child_thread_id = str(uuid.uuid4())
            # Create separate agent instance for each branch
            config = {"configurable": {"thread_id": child_thread_id}}
            # Start execution (async)
            asyncio.create_task(self._run_branch(child_thread_id, task, config))
            branches.append({
                "branch_id": str(uuid.uuid4()),
                "child_thread_id": child_thread_id,
                "task": task,
                "status": "running"
            })
            # Store in DB
            await self.store_branch(branches[-1], parent_thread_id)
        return branches
    
    async def _run_branch(self, thread_id: str, task: str, config: dict):
        """Execute a single branch"""
        try:
            result = await self.agent.ainvoke(
                {"messages": [("user", task)]},
                config=config
            )
            final = result["messages"][-1].content
            await self.update_branch(thread_id, "completed", final)
        except Exception as e:
            await self.update_branch(thread_id, "failed", str(e))
    
    async def merge_results(self, branches: list) -> str:
        """Merge results from all branches"""
        completed = [b for b in branches if b["status"] == "completed"]
        failed = [b for b in branches if b["status"] == "failed"]
        
        if not completed:
            return "All parallel tasks failed."
        
        merge_prompt = f"""
        Merge these parallel research results into a unified response:
        
        {chr(10).join(f"Task: {b['task']} Result: {b['result']}" for b in completed)}
        
        {f"Failed tasks: {[b['task'] for b in failed]}" if failed else ""}
        
        Provide a coherent, merged response.
        """
        # Use LLM to merge
        merged = await self.llm.ainvoke(merge_prompt)
        return merged.content
    
    async def check_all_complete(self, parent_thread_id: str) -> bool:
        """Check if all branches for a parent are done"""
        branches = await self.get_branches(parent_thread_id)
        return all(b["status"] in ("completed", "failed") for b in branches)
```

### Tool Definitions

```python
@tool
def spawn_parallel_tasks(tasks: list[str]) -> str:
    """Spawn multiple independent sub-tasks to run in parallel.
    
    Args:
        tasks: List of independent task descriptions
    """
    # 1. Detect if tasks are truly independent
    # 2. Spawn parallel agents
    # 3. Return branch IDs

@tool
def merge_parallel_results(branch_ids: list[str]) -> str:
    """Merge results from parallel branches.
    
    Args:
        branch_ids: List of branch IDs to merge
    """
    # 1. Wait for all branches to complete
    # 2. Merge results
    # 3. Return unified response
```

### Graph Changes

```python
# Modified graph structure:
#
#   agent → detect_parallel → (parallel) → spawn_branches → wait_for_merge → merge → done
#                           → (sequential) → tools → agent → done

def detect_parallel(state):
    """Detect if current step can be parallelized"""
    # Analyze agent's proposed actions
    # Return "parallel" or "sequential"

# Add parallel sub-graph
parallel_graph = StateGraph(AgentState)
parallel_graph.add_node("spawn", spawn_branches)
parallel_graph.add_node("wait", wait_for_completion)
parallel_graph.add_node("merge", merge_results)
parallel_graph.add_edge("spawn", "wait")
parallel_graph.add_conditional_edges("wait", check_completion, {
    "complete": "merge",
    "pending": "wait"
})
```

### API Endpoints

```
GET  /api/v1/branches/{thread_id}           — List branches for a thread
GET  /api/v1/branches/{branch_id}/status    — Check branch status
POST /api/v1/branches/merge                 — Manually trigger merge
```

### WebSocket Messages

```json
{ "type": "parallel_spawned", "branches": [...] }
{ "type": "branch_completed", "branch_id": "...", "task": "..." }
{ "type": "branch_failed", "branch_id": "...", "error": "..." }
{ "type": "merge_complete", "result": "..." }
```

### Frontend Changes

| File | Changes |
|------|---------|
| `app.component.ts` | Add `branches: BranchInfo[]`; handle parallel messages; add branch status display |
| `app.component.html` | Add parallel branches panel showing status of each sub-task with progress indicators |

### Execution Order

1. Create `app/agent/parallel.py`
2. Add parallel_branches table to startup
3. Add `spawn_parallel_tasks` and `merge_parallel_results` tools
4. Modify `app/agent/graph.py` — add parallel detection and sub-graph
5. Modify `app/main.py` — handle parallel WebSocket messages
6. Add API endpoints
7. Add frontend parallel display
8. Test with multi-step research prompts

---

## Phase 6: Tool Composition Chains

**Goal:** Agent creates reusable tool pipelines (like Unix pipes).

### Concept

Agent can compose multiple tools into a reusable chain:
1. "Search web → extract data → write to CSV" becomes a saved chain
2. Chains are stored and named
3. Reusable across conversations with different inputs
4. Chains can be listed, edited, and deleted

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS tool_chains (
    chain_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    steps TEXT NOT NULL,  -- JSON: [{"tool": "search_tool", "args_template": "{query}", "output_var": "results"}]
    input_vars TEXT NOT NULL,  -- JSON: ["query"]
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    usage_count INTEGER DEFAULT 0
);
```

### Files to Create

| File | Purpose |
|------|---------|
| `app/agent/chain.py` | Chain creation, execution, and management |

### Files to Modify

| File | Changes |
|------|---------|
| `app/agent/tools.py` | Add `create_chain`, `run_chain`, `list_chains`, `delete_chain` tools |
| `app/agent/graph.py` | Load chains on startup; add chain execution node |
| `app/main.py` | Add chain tables; add `GET /api/v1/chains` endpoint |
| `app/models.py` | Add `ChainInfo`, `ChainStep` models |

### Chain Manager (`chain.py`)

```python
class ChainManager:
    def __init__(self, workspace_dir: str, db_conn, all_tools):
        self.workspace_dir = workspace_dir
        self.conn = db_conn
        self.tools = {t.name: t for t in all_tools}
    
    async def create_chain(self, name: str, description: str, steps: list, input_vars: list) -> dict:
        """Create a new tool chain"""
        # Validate all tools exist
        # Validate step templates are valid Python
        # Store in DB
        return {"chain_id": str(uuid.uuid4()), "name": name, ...}
    
    async def run_chain(self, chain_id: str, input_values: dict) -> str:
        """Execute a chain with given inputs"""
        chain = await self.get_chain(chain_id)
        steps = json.loads(chain["steps"])
        
        context = input_values.copy()  # {query: "...", ...}
        outputs = []
        
        for i, step in enumerate(steps):
            tool = self.tools[step["tool"]]
            # Render args template with context
            args = render_template(step["args_template"], context)
            # Execute tool
            result = await tool.ainvoke(args)
            # Store result in context
            context[step.get("output_var", f"step_{i}_output")] = result
            outputs.append({"step": i, "tool": step["tool"], "result": result})
        
        # Update usage count
        await self.record_usage(chain_id)
        
        return format_chain_result(outputs)
    
    async def list_chains(self) -> list:
        """List all saved chains"""
        # SELECT * FROM tool_chains ORDER BY usage_count DESC
    
    async def delete_chain(self, chain_id: str) -> bool:
        """Delete a chain"""
        # DELETE FROM tool_chains WHERE chain_id = ?
    
    async def record_usage(self, chain_id: str):
        """Increment usage count"""
        # UPDATE tool_chains SET usage_count += 1, last_used_at = now
```

### Tool Definitions

```python
@tool
def create_chain(name: str, description: str, steps_json: str, input_vars_json: str) -> str:
    """Create a reusable tool chain from multiple tools.
    
    Args:
        name: Chain name (unique, snake_case)
        description: What the chain does
        steps_json: JSON array of steps, each with "tool", "args_template", "output_var"
        input_vars_json: JSON array of input variable names
    """
    # Parse and validate
    # Store chain
    # Return confirmation

@tool
def run_chain(chain_name: str, inputs_json: str) -> str:
    """Run a saved tool chain with given inputs.
    
    Args:
        chain_name: Name of the chain to run
        inputs_json: JSON object of input values
    """
    # Look up chain
    # Execute steps
    # Return final result

@tool
def list_chains() -> str:
    """List all saved tool chains with descriptions."""

@tool
def delete_chain(chain_name: str) -> str:
    """Delete a saved tool chain."""
```

### Chain Step Template Format

```json
{
    "steps": [
        {
            "tool": "search_tool",
            "args_template": "{query}",
            "output_var": "search_results"
        },
        {
            "tool": "e2b_sandbox_tool",
            "args_template": "import json\nresults = json.loads('{search_results}')\nprint(results)",
            "output_var": "processed"
        },
        {
            "tool": "write_file_tool",
            "args_template": "{output_filename}",
            "text_template": "{processed}",
            "output_var": "file_result"
        }
    ],
    "input_vars": ["query", "output_filename"]
}
```

### API Endpoints

```
GET  /api/v1/chains              — List all chains
GET  /api/v1/chains/{id}         — Get chain details
POST /api/v1/chains/test         — Test chain execution
DELETE /api/v1/chains/{id}       — Delete a chain
```

### WebSocket Messages

```json
{ "type": "chain_created", "name": "web_to_csv", "steps": 3 }
{ "type": "chain_step", "step": 1, "tool": "search_tool", "status": "running" }
{ "type": "chain_step_done", "step": 1, "tool": "search_tool", "status": "completed" }
{ "type": "chain_complete", "name": "web_to_csv", "result": "..." }
```

### Frontend Changes

| File | Changes |
|------|---------|
| `app.component.ts` | Add `chains: ChainInfo[]`; handle chain messages; add chain management panel |
| `app.component.html` | Add "Chains" section in sidebar showing saved chains with run/delete buttons |

### Execution Order

1. Create `app/agent/chain.py`
2. Add tool_chains table to startup
3. Add `create_chain`, `run_chain`, `list_chains`, `delete_chain` tools
4. Modify `app/agent/graph.py` — load chains on startup
5. Modify `app/main.py` — add chain API endpoints
6. Add frontend chain management
7. Test with multi-step workflows

---

## Cross-Cutting Concerns

### 1. Database Migration Strategy

All new tables use `CREATE TABLE IF NOT EXISTS` — safe for existing databases.

```python
# In main.py startup:
async def create_novelty_tables():
    tables = [
        """CREATE TABLE IF NOT EXISTS evolved_tools (...)""",
        """CREATE TABLE IF NOT EXISTS memory_patterns (...)""",
        """CREATE TABLE IF NOT EXISTS tool_reliability (...)""",
        """CREATE TABLE IF NOT EXISTS contrastive_examples (...)""",
        """CREATE TABLE IF NOT EXISTS parallel_branches (...)""",
        """CREATE TABLE IF NOT EXISTS tool_chains (...)""",
    ]
    for sql in tables:
        await graph.conn.execute(sql)
    await graph.conn.commit()
```

### 2. LLM Usage Budget

Phases 1, 2, 3, 4 all use LLM calls for meta-reasoning. Add budget tracking:

```python
class NoveltyBudget:
    MAX_META_CALLS_PER_REQUEST = 5  # Limit reflection/evolution calls
    
    def __init__(self):
        self.meta_calls = 0
    
    def can_make_meta_call(self) -> bool:
        return self.meta_calls < self.MAX_META_CALLS_PER_REQUEST
    
    def record_meta_call(self):
        self.meta_calls += 1
```

### 3. Configuration

Add to `.env`:

```env
# Novelty Features
EVOLVED_TOOLS_ENABLED=true
MEMORY_ENABLED=true
CONFIDENCE_THRESHOLD=0.6
REFLECTION_ENABLED=true
REFLECTION_MAX_RETRIES=2
PARALLEL_ENABLED=true
CHAINS_ENABLED=true
MEMORY_DECAY_LAMBDA=0.01
```

### 4. Performance Considerations

| Feature | Impact | Mitigation |
|---------|--------|------------|
| Self-Evolving Tools | LLM call + sandbox test | Cache tool code, limit creations |
| Memory Patterns | DB queries on startup | Load only high-strength patterns |
| Confidence Scoring | Extra node in graph | Lightweight scoring, no LLM |
| Contrastive Reflection | LLM call per request | Use small model (mistral-small) |
| Parallel Branching | Multiple concurrent agents | Limit max branches (3-5) |
| Tool Chains | Step-by-step execution | Cache chain definitions |

---

## Implementation Priority

| Priority | Phase | Reason |
|----------|-------|--------|
| 1 | Self-Evolving Tools | Highest demo value, builds on existing E2B |
| 2 | Contrastive Reflection | Improves quality, builds on existing HITL |
| 3 | Uncertainty Escalation | Improves safety, minimal new infrastructure |
| 4 | Cross-Thread Memory | Long-term learning, requires more testing |
| 5 | Tool Composition Chains | Useful but complex, can wait |
| 6 | Parallel Branching | Most complex, requires careful state management |

---

## Testing Strategy

### Unit Tests

```python
# tests/test_tool_evolver.py
- test_create_tool_validates_syntax
- test_create_tool_tests_in_sandbox
- test_create_tool_saves_to_disk
- test_load_tools_on_startup

# tests/test_memory.py
- test_extract_patterns_from_conversation
- test_apply_forgetting_curve
- test_query_relevant_patterns
- test_strengthen_existing_pattern

# tests/test_confidence.py
- test_score_tool_result_success
- test_score_tool_result_failure
- test_should_escalate_below_threshold
- test_update_reliability

# tests/test_contrastive.py
- test_reflect_generates_pairs
- test_store_examples
- test_query_relevant_examples

# tests/test_chain.py
- test_create_chain_validates_tools
- test_run_chain_executes_steps
- test_chain_renders_templates
```

### Integration Tests

```python
# tests/test_novelty_integration.py
- test_evolve_tool_and_use_in_new_conversation
- test_memory_persists_across_threads
- test_confidence_triggers_escalation
- test_reflection_improves_next_response
- test_chain_reusable_across_prompts
```

---

## Known Risks

1. **LLM Costs** — Meta-reasoning adds LLM calls per request. Mitigated by using mistral-small for reflection and limiting meta calls.

2. **Infinite Retry Loops** — Contrastive reflection with retry could loop. Mitigated by max 2 retries.

3. **Tool Evolution Errors** — Generated tools could be buggy. Mitigated by E2B sandbox testing before registration.

4. **Memory Bloat** — Too many patterns could slow queries. Mitigated by aggressive forgetting and cleanup.

5. **Parallel State Conflicts** — Multiple agents writing to same state. Mitigated by separate thread_ids per branch.

---

## Success Criteria

| Feature | Success Metric |
|---------|---------------|
| Self-Evolving Tools | Agent creates a working tool from a prompt |
| Cross-Thread Memory | Agent recalls a pattern from 3+ conversations ago |
| Uncertainty Escalation | Agent asks for help when confidence < 0.5 |
| Contrastive Reflection | Agent avoids a mistake it made before |
| Parallel Branching | Two research tasks complete faster than sequential |
| Tool Chains | Saved chain runs successfully with new inputs |
