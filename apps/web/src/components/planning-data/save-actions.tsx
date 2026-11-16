"use client";
import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import type { ButtonHTMLAttributes, ReactNode, RefObject } from "react";
import { firstFormProblem, revealInvalid } from "@/lib/forms/validation";

export type SaveFeedback = { tone: "info" | "success" | "error"; text: string; target?: { controls: string; label: string } };
type Action = { id: string; label: string; hint?: string; disabled: boolean; active: boolean; button: RefObject<HTMLButtonElement | null>; feedback?: SaveFeedback };
type Registry = { actions: Action[]; register: (action: Action) => () => void };
const RegistryContext = createContext<Registry | null>(null);
const ActiveContext = createContext(true);

export function BlockSaveProvider({ children }: { children: ReactNode }) {
  const [actions, setActions] = useState<Action[]>([]);
  const register = useCallback((action: Action) => {
    setActions((old) => [...old.filter((v) => v.id !== action.id), action]);
    return () => setActions((old) => old.filter((v) => v.id !== action.id));
  }, []);
  const value = useMemo(() => ({ actions, register }), [actions, register]);
  return <RegistryContext.Provider value={value}>{children}</RegistryContext.Provider>;
}
export function BlockSaveScope({ active, children }: { active: boolean; children: ReactNode }) {
  const parent = useContext(ActiveContext);
  return <ActiveContext.Provider value={parent && active}>{children}</ActiveContext.Provider>;
}
// The footer activates the real button. Native form validation, reviewed
// proposals and the original owner's pending-write checks stay in one place.
export function SaveActionButton({ saveLabel, saveHint, saveFeedback, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { saveLabel: string; saveHint?: string; saveFeedback?: SaveFeedback }) {
  const registry = useContext(RegistryContext), active = useContext(ActiveContext), id = useId();
  const button = useRef<HTMLButtonElement>(null), register = registry?.register;
  const [nativeError, setNativeError] = useState("");
  const feedbackText = nativeError || saveFeedback?.text, feedbackTone = nativeError ? "error" : saveFeedback?.tone,
    feedbackControls = nativeError ? undefined : saveFeedback?.target?.controls, feedbackTargetLabel = nativeError ? undefined : saveFeedback?.target?.label;
  useEffect(() => {
    const form = button.current?.form;
    if (!form || !active) return;
    const invalid = () => { const problem = firstFormProblem(form); if (problem) setNativeError(problem.text); };
    const changed = () => setNativeError("");
    form.addEventListener("invalid", invalid, true);
    form.addEventListener("input", changed); form.addEventListener("change", changed);
    return () => { form.removeEventListener("invalid", invalid, true); form.removeEventListener("input", changed); form.removeEventListener("change", changed); };
  }, [active, props.form]);
  useEffect(() => register?.({ id, label: saveLabel, hint: saveHint, disabled: !!props.disabled, active, button,
    feedback: feedbackText ? { text: feedbackText, tone: feedbackTone ?? "info",
      ...(feedbackControls && feedbackTargetLabel ? { target: { controls: feedbackControls, label: feedbackTargetLabel } } : {}) } : undefined }),
    [register, id, saveLabel, saveHint, props.disabled, active, feedbackText, feedbackTone, feedbackControls, feedbackTargetLabel]);
  return <><button {...props} ref={button} hidden={!!registry || props.hidden} tabIndex={registry ? -1 : props.tabIndex} data-block-save={saveLabel} onClick={event => {
    const source = event.currentTarget, form = source.form;
    if (source.type === "submit" && form && !form.noValidate && !source.formNoValidate) {
      const problem = firstFormProblem(form);
      if (problem) { event.preventDefault(); setNativeError(problem.text); revealInvalid(problem.control); return; }
    }
    setNativeError(""); props.onClick?.(event);
  }}>{children}</button>{!registry && nativeError && <p role="alert">{nativeError}</p>}</>;
}
export function SaveActionHint({ children }: { children: ReactNode }) {
  const registry = useContext(RegistryContext);
  return registry ? null : <p className="pt-save-hint">{children}</p>;
}
function Feedback({ action }: { action: Action }) {
  const element = useRef<HTMLDivElement>(null), text = action.feedback?.text, tone = action.feedback?.tone;
  useEffect(() => {
    if (!text || tone === "info" || !element.current || element.current.closest("[hidden]")) return;
    element.current.scrollIntoView({ block: "nearest" });
    if (tone === "error") element.current.focus({ preventScroll: true });
  }, [text, tone]);
  if (!action.feedback) return null;
  const { target } = action.feedback;
  return <div className="pt-save-feedback" data-state={tone} role={tone === "error" ? "alert" : "status"} tabIndex={-1} ref={element}>
    <p>{text}</p>
    {target && <button type="button" className="pt-button" onClick={() => {
      const root = action.button.current?.closest(".pt-setup-block, main") ?? document;
      const title = [...root.querySelectorAll<HTMLButtonElement>("button[aria-controls]")].find(button => button.getAttribute("aria-controls") === target.controls);
      title?.click();
      requestAnimationFrame(() => {
        const section = document.getElementById(target.controls);
        section?.scrollIntoView({ block: "start" });
        section?.querySelector<HTMLElement>("input, select, textarea")?.focus({ preventScroll: true });
      });
    }}>{target.label}</button>}
  </div>;
}
export function BlockSaveFooter({ emptyHint }: { emptyHint: string }) {
  const registry = useContext(RegistryContext), id = useId();
  const actions = registry?.actions.filter((a) => a.active) ?? [];
  return <div className="pt-block-save" aria-label="A blokk mentése">
    <div className="pt-block-save-buttons">
      {actions.length ? actions.map((action) => <button key={action.id} type="button" className="pt-primary" disabled={action.disabled}
        aria-describedby={action.hint ? `${id}-${action.id}` : undefined} onClick={() => {
          const source = action.button.current;
          if (source && !source.matches(":disabled")) source.click();
        }}>{action.label}</button>) : <button type="button" className="pt-primary" disabled aria-describedby={id}>Blokk mentése</button>}
    </div>
    {actions.length ? actions.map((action) => <div key={action.id}>
      {action.hint && <p id={`${id}-${action.id}`} className="pt-save-hint">{action.hint}</p>}
      <Feedback action={action} />
    </div>) : <p id={id} className="pt-save-hint">{emptyHint}</p>}
  </div>;
}
