import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "./context/AuthContext.jsx";
import { api } from "./api.js";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ChatWindow from "./components/ChatWindow.jsx";

export default function App() {
  const { token, checking, logout } = useAuth();
  const [authView, setAuthView] = useState("login");

  const [workspaces, setWorkspaces] = useState([]);
  const [normalThreads, setNormalThreads] = useState([]);
  const [workspaceThreads, setWorkspaceThreads] = useState({});

  const [activeThreadId, setActiveThreadId] = useState(null);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(null);
  const [activeThreadTitle, setActiveThreadTitle] = useState("");

  const refreshWorkspaces = useCallback(async () => {
    if (!token) return;
    const res = await api.listWorkspaces(token);
    setWorkspaces(res.workspaces);
  }, [token]);

  const refreshNormalThreads = useCallback(async () => {
    if (!token) return;
    const res = await api.listThreads(token, null);
    setNormalThreads(res.threads.filter((t) => !t.workspace_id));
  }, [token]);

  const refreshWorkspaceThreads = useCallback(
    async (workspaceId) => {
      if (!token) return;
      const res = await api.listThreads(token, workspaceId);
      setWorkspaceThreads((prev) => ({ ...prev, [workspaceId]: res.threads }));
    },
    [token]
  );

  useEffect(() => {
    if (token) {
      refreshWorkspaces();
      refreshNormalThreads();
    }
  }, [token, refreshWorkspaces, refreshNormalThreads]);

  function selectThread(threadId, workspaceId, explicitTitle) {
    setActiveThreadId(threadId);
    setActiveWorkspaceId(workspaceId);

    // When called right after creating a thread, the normalThreads /
    // workspaceThreads state hasn't re-rendered with the new entry yet
    // (setState is async), so looking it up here would find nothing and
    // silently fall back to "Chat". Passing the title explicitly at
    // creation time sidesteps that race entirely.
    if (explicitTitle) {
      setActiveThreadTitle(explicitTitle);
      return;
    }

    const list = workspaceId
      ? workspaceThreads[workspaceId] || []
      : normalThreads;
    const found = list.find((t) => t.thread_id === threadId);
    setActiveThreadTitle(found ? found.title : "Chat");
  }

  async function handleNewNormalChat() {
    const title = window.prompt("Name this chat:", "New chat");
    if (!title) return;
    const res = await api.createThread(token, title, null);
    await refreshNormalThreads();
    selectThread(res.thread_id, null, title);
  }

  async function handleNewWorkspace() {
    const name = window.prompt("Workspace name:", "New workspace");
    if (!name) return;
    await api.createWorkspace(token, name);
    await refreshWorkspaces();
  }

  async function handleSelectWorkspace(workspaceId) {
    setActiveWorkspaceId(workspaceId);
    await refreshWorkspaceThreads(workspaceId);
  }

  async function handleNewWorkspaceThread(workspaceId) {
    const title = window.prompt("Name this thread:", "New thread");
    if (!title) return;
    const res = await api.createThread(token, title, workspaceId);
    await refreshWorkspaceThreads(workspaceId);
    selectThread(res.thread_id, workspaceId, title);
  }

  if (checking) {
    return <div className="loading-screen">Loading…</div>;
  }

  if (!token) {
    return authView === "login" ? (
      <Login onSwitchToSignup={() => setAuthView("signup")} />
    ) : (
      <Signup onSwitchToLogin={() => setAuthView("login")} />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar
        workspaces={workspaces}
        normalThreads={normalThreads}
        workspaceThreads={workspaceThreads}
        activeThreadId={activeThreadId}
        activeWorkspaceId={activeWorkspaceId}
        onSelectThread={selectThread}
        onNewNormalChat={handleNewNormalChat}
        onNewWorkspace={handleNewWorkspace}
        onSelectWorkspace={handleSelectWorkspace}
        onNewWorkspaceThread={handleNewWorkspaceThread}
        onLogout={logout}
      />
      <ChatWindow
        threadId={activeThreadId}
        workspaceId={activeWorkspaceId}
        threadTitle={activeThreadTitle}
        isWorkspaceOwner={
          workspaces.find((w) => w.workspace_id === activeWorkspaceId)?.is_owner ?? true
        }
      />
    </div>
  );
}
