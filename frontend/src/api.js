const BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleJson(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  async signup(email, password) {
    const res = await fetch(`${BASE_URL}/api/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    return handleJson(res);
  },

  async login(email, password) {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);
    const res = await fetch(`${BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    return handleJson(res);
  },

  async me(token) {
    const res = await fetch(`${BASE_URL}/api/me`, {
      headers: authHeaders(token),
    });
    return handleJson(res);
  },

  async listWorkspaces(token) {
    const res = await fetch(`${BASE_URL}/api/workspaces`, {
      headers: authHeaders(token),
    });
    return handleJson(res);
  },

  async createWorkspace(token, name) {
    const res = await fetch(`${BASE_URL}/api/workspaces`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify({ name }),
    });
    return handleJson(res);
  },

  async listThreads(token, workspaceId) {
    const qs = workspaceId ? `?workspace_id=${workspaceId}` : "";
    const res = await fetch(`${BASE_URL}/api/threads${qs}`, {
      headers: authHeaders(token),
    });
    return handleJson(res);
  },

  async createThread(token, title, workspaceId) {
    const res = await fetch(`${BASE_URL}/api/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify({ title, workspace_id: workspaceId ?? null }),
    });
    return handleJson(res);
  },

  async deleteThread(token, threadId) {
    const res = await fetch(`${BASE_URL}/api/threads/${threadId}`, {
      method: "DELETE",
      headers: authHeaders(token),
    });
    return handleJson(res);
  },


  async listMessages(token, threadId) {
    const res = await fetch(`${BASE_URL}/api/messages?thread_id=${threadId}`, {
      headers: authHeaders(token),
    });
    return handleJson(res);
  },

  async uploadDocument(token, workspaceId, file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(
      `${BASE_URL}/api/workspaces/${workspaceId}/documents/upload`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: formData,
      }
    );
    return handleJson(res);
  },

  async uploadTranscript(token, workspaceId, file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(
      `${BASE_URL}/api/workspaces/${workspaceId}/documents/upload-transcript`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: formData,
      }
    );
    return handleJson(res);
  },

  async listDocuments(token, workspaceId) {
    const res = await fetch(
      `${BASE_URL}/api/workspaces/${workspaceId}/documents`,
      { headers: authHeaders(token) }
    );
    return handleJson(res);
  },

  async getSuggestedQuestions(token, workspaceId) {
    const res = await fetch(
      `${BASE_URL}/api/workspaces/${workspaceId}/suggested-questions`,
      { headers: authHeaders(token) }
    );
    return handleJson(res);
  },

  /**
   * Streams a chat response token by token.
   * onToken(text) fires per token, onDone() fires when the stream ends.
   * Returns an abort() function to cancel mid-stream.
   */
  streamChat(token, { threadId, workspaceId, question }, { onToken, onDone, onError }) {
    const controller = new AbortController();

    (async () => {
      try {
        const res = await fetch(`${BASE_URL}/api/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...authHeaders(token),
          },
          body: JSON.stringify({
            thread_id: threadId,
            workspace_id: workspaceId ?? null,
            question,
          }),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          const errBody = await res.json().catch(() => ({}));
          let errMsg = `Stream failed (${res.status})`;
          if (typeof errBody.detail === "string") {
            errMsg = errBody.detail;
          } else if (Array.isArray(errBody.detail)) {
            errMsg = errBody.detail.map((e) => e.msg || JSON.stringify(e)).join(", ");
          } else if (errBody.detail && typeof errBody.detail === "object") {
            errMsg = JSON.stringify(errBody.detail);
          }
          throw new Error(errMsg);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop(); // last (possibly incomplete) chunk stays in buffer

          for (const evt of events) {
            const line = evt.replace(/^data:\s*/, "").trim();
            if (!line) continue;
            // Defensive: if a chunk somehow arrives malformed or partial
            // despite the buffering above, skip just this one event rather
            // than letting an uncaught SyntaxError kill the entire stream.
            let parsed;
            try {
              parsed = JSON.parse(line);
            } catch {
              continue;
            }
            if (parsed.token !== undefined) {
              onToken(parsed.token);
            } else if (parsed.done) {
              onDone();
            }
          }
        }
      } catch (err) {
        if (err.name !== "AbortError") {
          onError(err.message || "Stream error");
        }
      }
    })();

    return () => controller.abort();
  },
};
