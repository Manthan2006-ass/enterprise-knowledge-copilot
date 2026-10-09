import React from "react";

/**
 * Shown when no thread is active. Guides the user on what to do next.
 */
export default function WelcomeScreen({
  workspaces,
  onNewNormalChat,
  onNewWorkspace,
  onSelectWorkspace,
  onNewWorkspaceThread,
}) {
  const ownedWorkspaces = workspaces.filter((w) => w.is_owner);
  const publicWorkspaces = workspaces.filter((w) => !w.is_owner);

  return (
    <div className="welcome-screen">
      <div className="welcome-hero">
        <div className="welcome-logo">✦</div>
        <h1 className="welcome-title">Enterprise Knowledge Copilot</h1>
        <p className="welcome-subtitle">
          Chat with AI — or ground it in your own documents for precise,
          citation-backed answers.
        </p>
      </div>

      <div className="welcome-cards">
        {/* Normal Chat CTA */}
        <button className="welcome-card" onClick={onNewNormalChat}>
          <span className="welcome-card-icon">💬</span>
          <div>
            <div className="welcome-card-title">Normal Chat</div>
            <div className="welcome-card-desc">
              Open-ended conversation with the AI — no documents needed.
            </div>
          </div>
        </button>

        {/* Create Workspace CTA */}
        <button className="welcome-card" onClick={onNewWorkspace}>
          <span className="welcome-card-icon">📁</span>
          <div>
            <div className="welcome-card-title">New Workspace</div>
            <div className="welcome-card-desc">
              Upload PDFs, DOCX, or lecture transcripts and chat grounded in
              your content.
            </div>
          </div>
        </button>
      </div>

      {/* Quick-access: existing workspaces */}
      {ownedWorkspaces.length > 0 && (
        <div className="welcome-workspaces">
          <p className="welcome-section-label">Your workspaces</p>
          <div className="welcome-ws-list">
            {ownedWorkspaces.map((ws) => (
              <button
                key={ws.workspace_id}
                className="welcome-ws-chip"
                onClick={() => onNewWorkspaceThread(ws.workspace_id)}
              >
                <span className="ws-chip-dot" />
                {ws.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Quick-access: shared/public workspaces */}
      {publicWorkspaces.length > 0 && (
        <div className="welcome-workspaces">
          <p className="welcome-section-label">Shared with you</p>
          <div className="welcome-ws-list">
            {publicWorkspaces.map((ws) => (
              <button
                key={ws.workspace_id}
                className="welcome-ws-chip shared"
                onClick={() => onNewWorkspaceThread(ws.workspace_id)}
              >
                <span className="ws-chip-dot shared" />
                {ws.name}
                <span className="ws-shared-badge">shared</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
