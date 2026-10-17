import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "react-hot-toast";
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

// Exact mapping of the 21 CampusX GenAI/LangChain lectures to their YouTube video IDs
export const LECTURE_VIDEO_MAP = {
  1: { id: "pSVk-5WemQ0", title: "GenAI Roadmap for Beginners" },
  2: { id: "_3ezSpJw2E8", title: "Generative AI using LangChain" },
  3: { id: "nlz9j-r0U9U", title: "Introduction to LangChain" },
  4: { id: "-xSJA8-o6Eg", title: "LangChain Components" },
  5: { id: "HdcLE8JuMrA", title: "LangChain Models Tutorial" },
  6: { id: "3TGqlQxpuU0", title: "Prompts in LangChain" },
  7: { id: "y5EmRr1O1h4", title: "Structured Output in LangChain" },
  8: { id: "Op6PbJZ5b2Q", title: "Output Parsers in LangChain" },
  9: { id: "5hjrPILA3-8", title: "Chains in LangChain" },
  10: { id: "u3b-W1NgYa4", title: "What are Runnables in LangChain" },
  11: { id: "47nc0n-e4_w", title: "Langchain Runnables Part 2" },
  12: { id: "bL92ALSZ2Cg", title: "Document Loaders in LangChain" },
  13: { id: "SEWS9P4ODmc", title: "Text Splitters in LangChain" },
  14: { id: "k13WK0bxQP0", title: "Vector Stores in LangChain" },
  15: { id: "pJdMxwXBsk0", title: "Retrievers in LangChain" },
  16: { id: "X0btK9X0Xnk", title: "Retrieval Augmented Generation (RAG)" },
  17: { id: "J5_-l7WIO_w", title: "YouTube Chatbot using LangChain" },
  18: { id: "etnLX7m2MiA", title: "Tools in LangChain" },
  19: { id: "EzYaFF7ahKw", title: "Tool Calling in LangChain" },
  20: { id: "gm_lQG8fYjI", title: "Building End-to-End AI Agent" },
  21: { id: "YcAYmIFtA0o", title: "Ollama Masterclass 2026" },
};

export function getLectureVideoUrl(lectureNum, timeStr) {
  const num = parseInt(lectureNum, 10);
  const entry = LECTURE_VIDEO_MAP[num];

  let totalSeconds = 0;
  if (timeStr) {
    const parts = timeStr.split(":").map(Number);
    if (parts.length === 2) {
      totalSeconds = (parts[0] || 0) * 60 + (parts[1] || 0);
    } else if (parts.length === 3) {
      totalSeconds = (parts[0] || 0) * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0);
    }
  }

  if (entry && entry.id) {
    return {
      youtubeUrl: `https://www.youtube.com/watch?v=${entry.id}&t=${totalSeconds}s`,
      embedUrl: `https://www.youtube.com/embed/${entry.id}?start=${totalSeconds}&autoplay=1`,
      title: entry.title,
      seconds: totalSeconds,
      lectureNum: num,
      timeStr,
    };
  }

  const query = encodeURIComponent(`CampusX Lecture ${lectureNum}`);
  return {
    youtubeUrl: `https://www.youtube.com/results?search_query=${query}`,
    embedUrl: null,
    title: `Lecture ${lectureNum}`,
    seconds: totalSeconds,
    lectureNum: num,
    timeStr,
  };
}

export default function ChatWindow({ threadId, workspaceId, threadTitle, isWorkspaceOwner = true }) {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [activeVideoCitation, setActiveVideoCitation] = useState(null);

  const markdownComponents = React.useMemo(() => ({
    a: ({ href, children }) => {
      if (href && href.startsWith("#citation:")) {
        const parts = href.replace("#citation:", "").split(":");
        const lecture = parts[0];
        const time = parts.slice(1).join(":");
        const citationData = getLectureVideoUrl(lecture, time);

        return (
          <a
            href={citationData.youtubeUrl}
            className="citation-chip clickable"
            onClick={(e) => {
              e.preventDefault();
              setActiveVideoCitation(citationData);
            }}
            title={`▶ Watch Lecture ${lecture} at ${time} · ${citationData.title}`}
          >
            {children}
            <span className="play-icon">▶</span>
          </a>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      );
    },
  }), []);
  const [uploading, setUploading] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);
  const fileInputRef = useRef(null);

  // Load message history whenever the active thread changes
  useEffect(() => {
    if (!threadId) return;
    setMessages([]);
    setStreamingText("");
    setSuggestedQuestions([]);
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

  // Fetch AI-generated suggested questions when opening a workspace thread
  // Only fires when there are no messages yet (fresh thread) so it doesn't
  // clutter an already-active conversation.
  useEffect(() => {
    if (!workspaceId || !threadId) return;
    // Don't re-fetch if we already have questions or messages loaded
    setSuggestedQuestions([]);
    setLoadingQuestions(true);
    api
      .getSuggestedQuestions(token, workspaceId)
      .then((res) => setSuggestedQuestions(res.questions || []))
      .catch(() => setSuggestedQuestions([]))
      .finally(() => setLoadingQuestions(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, threadId]);

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

  // Clicking a chip fills the input and sends immediately
  function handleChipClick(question) {
    setSuggestedQuestions([]);
    setInput("");
    if (isStreaming || sendingRef.current) return;
    sendingRef.current = true;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: question, created_at: new Date().toISOString() },
    ]);
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
            { role: "assistant", content: streamingTextRef.current, created_at: new Date().toISOString() },
          ]);
          setStreamingText("");
        },
        onError: (msg) => {
          sendingRef.current = false;
          setIsStreaming(false);
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: `Something went wrong: ${msg}`, created_at: new Date().toISOString() },
          ]);
          setStreamingText("");
        },
      }
    );
  }

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
      toast.success(`"${res.filename}" uploaded — ${res.chunks_indexed} chunks indexed`);
    } catch (err) {
      toast.error(err.message || "Upload failed");
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
      toast.success(`Transcript uploaded — ${res.chunks_indexed} chunks indexed`);
    } catch (err) {
      toast.error(err.message || "Transcript upload failed");
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

        {/* Magic Suggested Questions - shown only when chat is empty and workspace has docs */}
        {!isStreaming && messages.length === 0 && workspaceId && (
          <div className="suggested-questions">
            {loadingQuestions ? (
              <p className="sq-label">✨ Generating suggested questions…</p>
            ) : suggestedQuestions.length > 0 ? (
              <>
                <p className="sq-label">✨ Try asking:</p>
                <div className="sq-chips">
                  {suggestedQuestions.map((q, i) => (
                    <button
                      key={i}
                      className="sq-chip"
                      onClick={() => handleChipClick(q)}
                      disabled={isStreaming}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </>
            ) : null}
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

      {/* Interactive Video Citation Player Modal */}
      {activeVideoCitation && (
        <div
          className="video-modal-backdrop"
          onClick={() => setActiveVideoCitation(null)}
        >
          <div
            className="video-modal-card"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="video-modal-header">
              <div className="video-modal-meta">
                <span className="video-badge">
                  🎬 Lecture {activeVideoCitation.lectureNum}
                </span>
                <span className="timestamp-badge">
                  ⏱️ {activeVideoCitation.timeStr}
                </span>
                <span className="video-modal-title">
                  {activeVideoCitation.title}
                </span>
              </div>
              <button
                type="button"
                className="video-modal-close"
                onClick={() => setActiveVideoCitation(null)}
                aria-label="Close video player"
              >
                ✕
              </button>
            </div>

            <div className="video-modal-body">
              {activeVideoCitation.embedUrl ? (
                <iframe
                  className="video-iframe"
                  src={activeVideoCitation.embedUrl}
                  title={activeVideoCitation.title}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              ) : (
                <div className="video-fallback">
                  <p>Direct video preview unavailable.</p>
                </div>
              )}
            </div>

            <div className="video-modal-footer">
              <span className="video-footer-tip">
                💡 Playing automatically from timestamp <strong>{activeVideoCitation.timeStr}</strong>
              </span>
              <a
                href={activeVideoCitation.youtubeUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-open-youtube"
              >
                Open on YouTube ↗
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
