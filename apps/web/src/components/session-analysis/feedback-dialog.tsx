"use client";
import { useEffect, useRef, useState } from "react";
import { loadFeedback } from "@/lib/session-analysis/feedback";
import { FeedbackPanel } from "./feedback";
export const promptKey = (owner: string, session: string) =>
  `paddletrainer:feedback-prompt:v1:${owner}:${session}`;
export function FeedbackDialog({
  owner,
  session,
  onSaved,
}: {
  owner: string;
  session: string;
  onSaved: () => void;
}) {
  const [open, setOpen] = useState(false),
    [notice, setNotice] = useState("");
  const dialog = useRef<HTMLDialogElement>(null),
    trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const abort = new AbortController();
    loadFeedback(owner, session, abort.signal)
      .then((context) => {
        if (
          abort.signal.aborted ||
          Object.values(context.current).some(Boolean)
        )
          return;
        try {
          if (localStorage.getItem(promptKey(owner, session)) !== "seen")
            setOpen(true);
        } catch {
          setNotice(
            "Az automatikus emlékeztető most nem jegyezhető meg. A visszajelzés gombbal bármikor elérhető.",
          );
        }
      })
      .catch(() => {
        /* The explicit button can retry loading, without a blocking popup. */
      });
    return () => abort.abort();
  }, [owner, session]);
  useEffect(() => {
    if (!open) return;
    const node = dialog.current;
    node?.showModal();
    return () => node?.close();
  }, [open]);
  function close() {
    try {
      localStorage.setItem(promptKey(owner, session), "seen");
    } catch {
      setNotice("Az emlékeztető elhalasztása most nem jegyezhető meg.");
    }
    setOpen(false);
    trigger.current?.focus();
  }
  return (
    <div className="pt-feedback-launcher">
      <button
        ref={trigger}
        type="button"
        className="pt-button"
        onClick={() => setOpen(true)}
      >
        Saját visszajelzés
      </button>
      {notice && <small role="status">{notice}</small>}
      {open && (
        <dialog
          className="pt-quick-dialog pt-feedback-dialog"
          ref={dialog}
          aria-label="Saját edzésvisszajelzés"
          onCancel={(event) => {
            event.preventDefault();
            close();
          }}
        >
          <div className="pt-quick-header">
            <strong>Hogyan érezted magad?</strong>
            <button type="button" className="pt-button" onClick={close}>
              Most kihagyom / Bezárás
            </button>
          </div>
          <FeedbackPanel
            owner={owner}
            session={session}
            showLearning={false}
            onSaved={() => {
              try {
                localStorage.setItem(promptKey(owner, session), "seen");
              } catch {
                /* The server receipt still establishes saved feedback. */
              }
              onSaved();
            }}
          />
        </dialog>
      )}
    </div>
  );
}
