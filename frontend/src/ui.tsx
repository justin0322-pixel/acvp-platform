import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Disposition } from "./api/types";

export function Button(
  { variant = "primary", loading, children, className = "", ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "soft"; loading?: boolean },
) {
  return (
    <button className={`btn btn-${variant} ${className}`} disabled={p.disabled || loading} {...p}>
      {loading && <span className="spin" />}
      {children}
    </button>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function StepHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="step-head">
      <div className="eyebrow">{eyebrow}</div>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
    </div>
  );
}

export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export function Notice({ kind = "info", children }: { kind?: "info" | "err" | "ok"; children: ReactNode }) {
  return <div className={`notice ${kind}`}>{children}</div>;
}

/** Disposition / session status → coloured badge. */
const DISPO: Record<Disposition | "pending", { cls: string; label: string }> = {
  passed: { cls: "ok", label: "passed" },
  failed: { cls: "bad", label: "failed" },
  error: { cls: "bad", label: "error" },
  incomplete: { cls: "warn", label: "incomplete" },
  unreceived: { cls: "muted", label: "unreceived" },
  missing: { cls: "warn", label: "missing" },
  expired: { cls: "muted", label: "expired" },
  pending: { cls: "info", label: "pending" },
};
export function StatusBadge({ status }: { status: Disposition | "pending" }) {
  const s = DISPO[status] ?? { cls: "muted", label: status };
  return <span className={`badge ${s.cls}`}>{s.label}</span>;
}
