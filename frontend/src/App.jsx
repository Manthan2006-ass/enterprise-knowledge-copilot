import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "./context/AuthContext.jsx";
import { api } from "./api.js";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import WelcomeScreen from "./components/WelcomeScreen.jsx";
import Modal from "./components/Modal.jsx";
import { Toaster, toast } from "react-hot-toast";

export default function App() {
  const { token, checking, logout } = useAuth();
  const [authView, setAuthView] = useState("login");

  const [workspaces, setWorkspaces] = useState([]);
  const [normalThreads, setNormalThreads] = useState([]);
  const [workspaceThreads, setWorkspaceThreads] = useState({});

  const [activeThreadId, setActiveThreadId] = useState(null);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(null);
  const [activeThreadTitle, setActiveThreadTitle] = useState("");

  // Modal state — which modal is open and for which workspace
  const [modal, setModal] = useState(null);
  // modal = { type: "normal-chat" | "new-workspace" | "new-thread", workspaceId?: string }

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

  // ---- Modal confirm handlers ----

  async function handleConfirmNormalChat(title) {
    setModal(null);
    const res = await api.createThread(token, title, null);
    await refreshNormalThreads();
    selectThread(res.thread_id, null, title);
  }

  async function handleConfirmNewWorkspace(name) {
    setModal(null);
    await api.createWorkspace(token, name);
    await refreshWorkspaces();
  }

  async function handleConfirmNewThread(title) {
    const workspaceId = modal?.workspaceId;
    setModal(null);
    if (!workspaceId) return;
    const res = await api.createThread(token, title, workspaceId);
    await refreshWorkspaceThreads(workspaceId);
    selectThread(res.thread_id, workspaceId, title);
  }

  // ---- Trigger modal opens ----

  function handleNewNormalChat() {
    setModal({ type: "normal-chat" });
  }

  function handleNewWorkspace() {
    setModal({ type: "new-workspace" });
  }

  async function handleSelectWorkspace(workspaceId) {
    setActiveWorkspaceId(workspaceId);
    await refreshWorkspaceThreads(workspaceId);
  }

  function handleNewWorkspaceThread(workspaceId) {
    setModal({ type: "new-thread", workspaceId });
  }

  async function handleDeleteThread(threadId, workspaceId) {
    try {
      await api.deleteThread(token, threadId);
      // If the deleted thread was active, clear the view
      if (activeThreadId === threadId) {
        setActiveThreadId(null);
        setActiveWorkspaceId(null);
        setActiveThreadTitle("");
      }
      // Refresh the correct thread list
      if (workspaceId) {
        await refreshWorkspaceThreads(workspaceId);
      } else {
        await refreshNormalThreads();
      }
      toast.success("Thread deleted");
    } catch (err) {
      toast.error(err.message || "Failed to delete thread");
    }
  }

  // ---- Modal rendering logic ----

  function renderModal() {
    if (!modal) return null;
    if (modal.type === "normal-chat") {
      return (
        <Modal
          title="Start a new chat"
          placeholder="Give this conversation a name…"
          onConfirm={handleConfirmNormalChat}
          onClose={() => setModal(null)}
        />
      );
    }
    if (modal.type === "new-workspace") {
      return (
        <Modal
          title="Create a workspace"
          placeholder="e.g. My AI Project Notes"
          onConfirm={handleConfirmNewWorkspace}
          onClose={() => setModal(null)}
        />
      );
    }
    if (modal.type === "new-thread") {
      return (
        <Modal
          title="New thread"
          placeholder="Give this thread a name…"
          onConfirm={handleConfirmNewThread}
          onClose={() => setModal(null)}
        />
      );
    }
    return null;
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
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: { fontFamily: "Inter, sans-serif", fontSize: "13.5px" },
          success: { iconTheme: { primary: "#5b7f62", secondary: "#fff" } },
        }}
      />
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
        onDeleteThread={handleDeleteThread}
        onLogout={logout}
      />

      {/* Show welcome screen when no thread is selected */}
      {!activeThreadId ? (
        <WelcomeScreen
          workspaces={workspaces}
          onNewNormalChat={handleNewNormalChat}
          onNewWorkspace={handleNewWorkspace}
          onSelectWorkspace={handleSelectWorkspace}
          onNewWorkspaceThread={handleNewWorkspaceThread}
        />
      ) : (
        <ChatWindow
          threadId={activeThreadId}
          workspaceId={activeWorkspaceId}
          threadTitle={activeThreadTitle}
          isWorkspaceOwner={
            workspaces.find((w) => w.workspace_id === activeWorkspaceId)
              ?.is_owner ?? true
          }
        />
      )}

      {/* Modal overlay — rendered on top of everything */}
      {renderModal()}
    </div>
  );
}
