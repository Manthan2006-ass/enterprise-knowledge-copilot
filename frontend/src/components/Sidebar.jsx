import React, { useState } from "react";

export default function Sidebar({
  workspaces,
  normalThreads,
  workspaceThreads,
  activeThreadId,
  activeWorkspaceId,
  onSelectThread,
  onNewNormalChat,
  onNewWorkspace,
  onSelectWorkspace,
  onNewWorkspaceThread,
  onDeleteThread,
  onLogout,
}) {
  const [expandedWs, setExpandedWs] = useState(activeWorkspaceId);

  function toggleWorkspace(wsId) {
    const next = expandedWs === wsId ? null : wsId;
    setExpandedWs(next);
    if (next) onSelectWorkspace(next);
  }

  function handleDelete(e, threadId, workspaceId) {
    // Stop the click from also selecting the thread
    e.stopPropagation();
    onDeleteThread(threadId, workspaceId ?? null);
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-wordmark">Copilot</span>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-head">
          <span>Normal Chats</span>
          <button className="icon-btn" onClick={onNewNormalChat} title="New chat">
            +
          </button>
        </div>
        <ul className="thread-list">
          {normalThreads.map((t) => (
            <li
              key={t.thread_id}
              className={`thread-item ${t.thread_id === activeThreadId ? "active" : ""}`}
              onClick={() => onSelectThread(t.thread_id, null)}
            >
              <span className="thread-title">{t.title}</span>
              <button
                className="thread-delete-btn"
                title="Delete thread"
                onClick={(e) => handleDelete(e, t.thread_id, null)}
              >
                ×
              </button>
            </li>
          ))}
          {normalThreads.length === 0 && (
            <li className="thread-empty">No chats yet</li>
          )}
        </ul>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-head">
          <span>Workspaces</span>
          <button className="icon-btn" onClick={onNewWorkspace} title="New workspace">
            +
          </button>
        </div>
        <ul className="workspace-list">
          {workspaces.map((ws) => (
            <li key={ws.workspace_id}>
              <div
                className={`workspace-item ${expandedWs === ws.workspace_id ? "expanded" : ""}`}
                onClick={() => toggleWorkspace(ws.workspace_id)}
              >
                <span className="workspace-dot" />
                {ws.name}
                {!ws.is_owner && <span className="ws-badge">shared</span>}
              </div>
              {expandedWs === ws.workspace_id && (
                <ul className="thread-list nested">
                  {(workspaceThreads[ws.workspace_id] || []).map((t) => (
                    <li
                      key={t.thread_id}
                      className={`thread-item ws ${t.thread_id === activeThreadId ? "active" : ""}`}
                      onClick={() => onSelectThread(t.thread_id, ws.workspace_id)}
                    >
                      <span className="thread-title">{t.title}</span>
                      <button
                        className="thread-delete-btn"
                        title="Delete thread"
                        onClick={(e) => handleDelete(e, t.thread_id, ws.workspace_id)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                  <li
                    className="thread-item new-thread"
                    onClick={() => onNewWorkspaceThread(ws.workspace_id)}
                  >
                    + New thread
                  </li>
                </ul>
              )}
            </li>
          ))}
          {workspaces.length === 0 && (
            <li className="thread-empty">No workspaces yet</li>
          )}
        </ul>
      </div>

      <button className="logout-btn" onClick={onLogout}>
        Sign out
      </button>
    </aside>
  );
}
