# Frontend Setup

## 1. Place this folder
Put this entire `frontend/` folder into your `enterprise-copilot/` project root,
alongside `backend/` (replace your existing empty `frontend/` folder).

## 2. Install dependencies
```bash
cd frontend
npm install
```

## 3. Make sure your backend is running
In a separate terminal:
```bash
cd backend
uvicorn main:app --reload
```
The frontend expects the API at `http://127.0.0.1:8000` (hardcoded in `src/api.js` —
change `BASE_URL` there if your backend runs elsewhere).

## 4. Run the frontend
```bash
npm run dev
```
Open the URL it prints (usually `http://localhost:5173`).

## What you'll see
- **Signup/Login screen** first
- After logging in: a dark sidebar with **Normal Chats** at top and **Workspaces** below
- Click **+** next to "Normal Chats" to start a plain conversation (no RAG)
- Click **+** next to "Workspaces" to create a workspace, then click it to expand
  and see **+ New thread** to start a workspace-scoped chat
- Inside a workspace thread, an **Upload document** button appears — upload a
  `.pdf`, `.docx`, or `.txt` and it gets embedded into that workspace immediately
- Ask a question in a workspace thread — tokens stream in live, and a strip above
  the chat shows which documents are indexed in that workspace
- The sage-green dot next to workspace names, and the "grounded in your documents"
  label, are the only visual cues distinguishing RAG threads from normal ones —
  intentionally minimal, since that's the one thing that actually differs

## Known limitations (intentional, for now)
- No password reset, no email verification
- `window.prompt()` is used for naming chats/workspaces — functional but not
  polished; swap for a proper modal when you want to make this presentable
- Token stored in `localStorage` — fine for a personal/demo project, but note
  this doesn't survive an XSS attack the way an httpOnly cookie would; revisit
  before any real deployment with real user data
- No pagination on thread/message lists — fine at small scale, will need it
  once threads pile up

## Next steps once this is running
- Test the whole flow end to end: signup → create workspace → upload doc →
  ask a question → confirm it answers from the document
- Test Normal Chat side by side to confirm no RAG bleed-through
- Then revisit the "production grade" checklist from earlier: Docker, tests,
  rate limiting, etc. — much easier to prioritize once you have a working app
  to actually use.
