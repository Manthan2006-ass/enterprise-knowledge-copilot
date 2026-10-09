import React, { useEffect, useRef } from "react";

/**
 * A clean inline modal that replaces window.prompt().
 * Usage: <Modal title="..." placeholder="..." onConfirm={fn} onClose={fn} />
 */
export default function Modal({ title, placeholder, onConfirm, onClose }) {
  const inputRef = useRef(null);

  // Auto-focus the input when the modal opens
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function handleSubmit(e) {
    e.preventDefault();
    const val = inputRef.current?.value?.trim();
    if (val) onConfirm(val);
  }

  // Close on backdrop click
  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose();
  }

  // Close on Escape key
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={handleBackdrop}>
      <div className="modal-card">
        <h3 className="modal-title">{title}</h3>
        <form onSubmit={handleSubmit} className="modal-form">
          <input
            ref={inputRef}
            type="text"
            className="modal-input"
            placeholder={placeholder}
            maxLength={80}
          />
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
