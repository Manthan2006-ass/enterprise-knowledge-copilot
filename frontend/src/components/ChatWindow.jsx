import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";
import { useAuth } from "../context/AuthContext.jsx";

// Converts a raw [Lecture 11 at 03:15] citation into a special markdown link
// syntax first, then intercepts that link type in ReactMarkdown's renderer
// below to display it as a styled chip instead of a plain URL. This keeps
// citations inline with the surrounding sentence rather than breaking them
// into separate blocks, since links are inline markdown elements.
// The model doesn't always follow the exact "[Lecture 11 at 03:15]" format
// it's instructed to use - it often falls back to echoing the raw source
// header style instead, e.g. "Lecture 14 - Vector Stores in LangChain | ...
// | CampusX [00:00-01:20]". Rather than keep fighting a small model's
// instruction-following limits, the parser matches BOTH styles: it prefers
// the ideal format when present, and falls back to extracting lecture
// number + timestamp from the looser style otherwise.
const IDEAL_CITATION_TEST = /\[Lecture\s+(\d+)\s+at\s+(\d{2}:\d{2})\]/;
const IDEAL_CITATION_GLOBAL = /\[Lecture\s+(\d+)\s+at\s+(\d{2}:\d{2})\]/g;

// Non-greedy, capped lookahead so one citation's bracket can't accidentally
// swallow text up to a LATER, unrelated citation's bracket.
const FALLBACK_CITATION_GLOBAL = /Lecture\s+(\d+)[\s\S]{0,150}?\[(\d{2}:\d{2})(?:-\d{2}:\d{2})?\]/g;

function injectCitationLinks(text) {
  const chipify = (_match, lecture, time) =>
    `[🎬 Lecture ${lecture} · ⏱️ ${time}](#citation:${lecture}:${time})`;

  if (IDEAL_CITATION_TEST.test(text)) {
    return text.replace(IDEAL_CITATION_GLOBAL, chipify);
  }
  return text.replace(FALLBACK_CITATION_GLOBAL, chipify);
}

// Custom renderer passed to ReactMarkdown - only special-cases links whose
// href we generated above (#citation:...); every other link renders normally.
const markdownComponents = {
  a: ({ href, children }) => {
    if (href && href.startsWith("#citation:")) {
      return (
        <span
          className="citation-chip"
          onClick={(e) => e.preventDefault()}
        >
          {children}
        </span>
      );
    }
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  },
};

export default function ChatWindow({ threadId, workspaceId, threadTitle, isWorkspaceOwner = true }) {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const fileInputRef = useRef(null);

  // Load message history whenever the active thread changes
  useEffect(() => {
    if (!threadId) return;
    setMessages([]);
    setStreamingText("");
    api
      .listMessages(token, threadId)
      .then((res) => setMessages(res.messages))
      .catch(() => {});

    if (workspaceId) {
      api
        .listDocuments(token, workspaceId)
        .then((res) => setDocuments(res.documents))
        .catch(() => {});
    } else {
      setDocuments([]);
    }

    return () => {
      if (abortRef.current) abortRef.current();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, workspaceId]);

  useEffect(() => {
    if (!scrollRef.current) return;
    // Smooth scrolling triggers layout recalculation - firing it on every
    // single token during streaming (dozens of times per second) causes
    // visible jitter. Use an instant jump while streaming, save smooth
    // scrolling for when a message is first sent/received.
    if (isStreaming) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    } else {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, streamingText, isStreaming]);

  const sendingRef = useRef(false);

  function handleSend(e) {
    e.preventDefault();
    const question = input.trim();
    // sendingRef is a ref, not state — it updates synchronously, so even if
    // handleSend somehow fires twice in the same event-loop tick (fast
    // double-click, Enter + click racing), the second call sees the guard
    // immediately instead of reading a stale pre-update isStreaming value.
    if (!question || isStreaming || sendingRef.current) return;
    sendingRef.current = true;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: question, created_at: new Date().toISOString() },
    ]);
    setInput("");
    setStreamingText("");
    setIsStreaming(true);

    abortRef.current = api.streamChat(
      token,
      { threadId, workspaceId, question },
      {
        onToken: (tok) => setStreamingText((prev) => prev + tok),
        onDone: () => {
          sendingRef.current = false;
          setIsStreaming(false);
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: streamingTextRef.current,
              created_at: new Date().toISOString(),
            },
          ]);
          setStreamingText("");
        },
        onError: (msg) => {
          sendingRef.current = false;
          setIsStreaming(false);
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `Something went wrong: ${msg}`,
              created_at: new Date().toISOString(),
            },
          ]);
          setStreamingText("");
        },
      }
    );
  }

  // Keep a ref in sync so onDone can read the final streamed text
  // without a stale closure over streamingText.
  const streamingTextRef = useRef("");
  useEffect(() => {
    streamingTextRef.current = streamingText;
  }, [streamingText]);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file || !workspaceId) return;
    setUploading(true);
    setUploadError("");
    try {
      const res = await api.uploadDocument(token, workspaceId, file);
      setDocuments((prev) => [
        ...prev,
        {
          doc_id: res.doc_id,
          filename: res.filename,
          chunk_count: res.chunks_indexed,
          uploaded_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  const transcriptInputRef = useRef(null);
  const [uploadingTranscript, setUploadingTranscript] = useState(false);

  async function handleTranscriptUpload(e) {
    const file = e.target.files?.[0];
    if (!file || !workspaceId) return;
    setUploadingTranscript(true);
    setUploadError("");
    try {
      const res = await api.uploadTranscript(token, workspaceId, file);
      setDocuments((prev) => [
        ...prev,
        {
          doc_id: res.doc_id,
          filename: res.filename,
          chunk_count: res.chunks_indexed,
          uploaded_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploadingTranscript(false);
      if (transcriptInputRef.current) transcriptInputRef.current.value = "";
    }
  }

  if (!threadId) {
    return (
      <div className="chat-empty">
        <p>Select a chat or start a new one.</p>
      </div>
    );
  }

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div>
          <h2>{threadTitle}</h2>
          <span className={`chat-mode ${workspaceId ? "ws" : "normal"}`}>
            {workspaceId ? "Workspace · grounded in your documents" : "Normal chat"}
            {workspaceId && !isWorkspaceOwner && " · shared, view-only"}
          </span>
        </div>
        {workspaceId && isWorkspaceOwner && (
          <div className="upload-controls">
            <input
              type="file"
              ref={fileInputRef}
              accept=".pdf,.docx,.txt"
              onChange={handleUpload}
              style={{ display: "none" }}
            />
            <button
              className="btn-secondary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? "Uploading…" : "Upload document"}
            </button>

            <input
              type="file"
              ref={transcriptInputRef}
              accept=".json"
              onChange={handleTranscriptUpload}
              style={{ display: "none" }}
            />
            <button
              className="btn-secondary"
              onClick={() => transcriptInputRef.current?.click()}
              disabled={uploadingTranscript}
              title="Upload a pre-transcribed lecture JSON (with timestamps)"
            >
              {uploadingTranscript ? "Uploading…" : "Upload transcript"}
            </button>
          </div>
        )}
      </div>

      {workspaceId && documents.length > 0 && (
        <div className="doc-strip">
          {documents.map((d) => (
            <span key={d.doc_id} className="doc-pill">
              {d.filename} · {d.chunk_count} chunks
            </span>
          ))}
        </div>
      )}
      {uploadError && <div className="auth-error small">{uploadError}</div>}

      <div className="messages" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            <div className="bubble-role">{m.role === "user" ? "You" : "Copilot"}</div>
            <div className="bubble-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {injectCitationLinks(m.content)}
              </ReactMarkdown>
            </div>
          </div>
        ))}
        {isStreaming && (
          <div className="bubble assistant">
            <div className="bubble-role">Copilot</div>
            <div className="bubble-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {injectCitationLinks(streamingText)}
              </ReactMarkdown>
              <span className="cursor" />
            </div>
          </div>
        )}
      </div>

      <form className="composer" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            workspaceId
              ? "Ask something about this workspace's documents…"
              : "Ask anything…"
          }
          disabled={isStreaming}
        />
        <button type="submit" className="btn-primary" disabled={isStreaming || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
