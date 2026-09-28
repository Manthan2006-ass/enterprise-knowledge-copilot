# Running the tests

## Setup
```bash
cd backend
pip install -r requirements.txt
```

## What's required to run these
- **MongoDB must be running** (same as normal dev) - tests use a SEPARATE
  database (`enterprise_copilot_test_db`, set automatically in
  `tests/conftest.py`), so they never touch or wipe your real dev data.
- **Ollama does NOT need to be running.** Every test here only exercises
  paths that return before any Ollama/ChromaDB call happens (auth checks,
  ownership checks, 404s). That's intentional - see the note in
  `test_chat_ownership.py` for what's deliberately NOT covered yet.

## Run everything
```bash
pytest
```

## Run one file
```bash
pytest tests/test_auth.py
```

## Run with more detail
```bash
pytest -v
```

## What's covered
- Signup, duplicate-email rejection, login, wrong-password rejection, JWT validation
- Workspace creation and per-user listing
- Thread creation (normal + workspace), bad/missing workspace_id handling
- Message creation, listing, thread-ownership checks
- **Cross-user isolation** across threads, messages, document uploads, document
  listing, and the chat-stream ownership check - the core guarantee of the
  whole app, each as its own explicit test

## What's NOT covered yet (documented, not forgotten)
Full RAG behavior - actual retrieval correctness, the has_docs empty-workspace
fallback, distance-threshold filtering, real streamed answers - needs a live
Ollama + populated ChromaDB, which makes these slower, environment-dependent
integration tests rather than fast unit tests. If you want to add these:
1. Mark them with `@pytest.mark.integration`
2. Register that marker in `pytest.ini`
3. Run fast tests locally with `pytest -m "not integration"`, and run the
   full suite (including integration) only in CI or before a deploy, where
   Ollama is guaranteed to be running.

## Before you commit
Run `pytest` once, confirm everything passes, and consider adding a GitHub
Actions workflow that runs this automatically on every push - that's the next
natural step after having a suite at all.
