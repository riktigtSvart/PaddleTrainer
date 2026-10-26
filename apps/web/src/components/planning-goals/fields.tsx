import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
export const buttonClass =
  "pt-primary rounded-lg px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40";
export const secondaryClass =
  "rounded-lg border border-zinc-600 px-4 py-2 text-sm text-zinc-100 hover:bg-zinc-800 disabled:opacity-40";
const fieldClass =
  "mt-2 block w-full rounded-lg border border-zinc-600 bg-zinc-950 px-3 py-2.5 text-base text-zinc-100 outline-none focus:border-teal-300 focus:ring-1 focus:ring-teal-300 disabled:opacity-60";
export function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block text-sm text-zinc-200">
      {label}
      <input className={fieldClass} maxLength={4000} {...props} />
      {hint && (
        <span className="mt-1 block text-xs leading-5 text-zinc-400">
          {hint}
        </span>
      )}
    </label>
  );
}
export function Area({
  label,
  ...props
}: { label: string } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <label className="block text-sm text-zinc-200">
      {label}
      <textarea className={fieldClass} rows={3} maxLength={4000} {...props} />
    </label>
  );
}
export function Select({
  label,
  children,
  ...props
}: {
  label: string;
  children: ReactNode;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <label className="block text-sm text-zinc-200">
      {label}
      <select className={fieldClass} {...props}>
        {children}
      </select>
    </label>
  );
}
export function Card({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-zinc-700 bg-zinc-900/70 p-5 sm:p-7">
      <h2 className="mb-5 text-xl font-semibold text-zinc-100">{title}</h2>
      {children}
    </section>
  );
}
export function Message({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      role={error ? "alert" : "status"}
      className={`rounded-xl border p-4 text-sm leading-6 ${error ? "border-amber-500/60 bg-amber-950/30 text-amber-100" : "border-teal-500/50 bg-teal-950/30 text-teal-100"}`}
    >
      {children}
    </div>
  );
}
