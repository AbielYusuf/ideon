"use client";

import type { ReactNode } from "react";

export const ACTIVITY_TYPES = [
  "SEO Update",
  "Content Update",
  "CTA Update",
  "Technical Fix",
  "Internal Linking",
  "Other",
] as const;

export function todayIso(): string {
  return toIsoDate(new Date());
}

export function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseIsoDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month ?? 1) - 1, day ?? 1);
}

const longDateFormatter = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
});

const shortDateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

export function formatLongDate(value: string | null): string {
  if (!value) return "—";
  return longDateFormatter.format(parseIsoDate(value));
}

export function formatShortDate(value: string | null): string {
  if (!value) return "—";
  return shortDateFormatter.format(parseIsoDate(value));
}

export function formatMonth(value: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
  }).format(value);
}

export function StatusBadge({
  status,
  compact = false,
}: {
  status: "planned" | "completed";
  compact?: boolean;
}) {
  const styles =
    status === "planned"
      ? "border-[#A52A42]/50 bg-[#8E2638]/15 text-[#E58A9B]"
      : "border-[#77777D]/40 bg-[#222124] text-[#E8E3DC]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-mono uppercase tracking-widest ${styles} ${
        compact ? "px-2 py-0.5 text-[9px]" : "px-2.5 py-0.5 text-[10px]"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          status === "planned" ? "bg-[#A52A42]" : "bg-[#E8E3DC]"
        }`}
      />
      {status}
    </span>
  );
}

export function Modal({
  title,
  eyebrow,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  eyebrow?: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-[#171719]/80 px-4 py-8 backdrop-blur-sm">
      <div
        className={`w-full rounded-lg border border-[#77777D]/30 bg-[#1C1B1E] shadow-2xl ${
          wide ? "max-w-3xl" : "max-w-xl"
        }`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#222124] px-5 py-4">
          <div>
            {eyebrow ? (
              <p className="font-mono text-[10px] uppercase tracking-widest text-[#8E2638]">
                {eyebrow}
              </p>
            ) : null}
            <h2 className="mt-0.5 text-lg font-medium text-[#F5F2EE]">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded border border-[#77777D]/30 px-2.5 py-1 font-mono text-xs text-[#A6A1A0] transition-colors hover:border-[#77777D]/60 hover:text-[#F5F2EE]"
          >
            ESC
          </button>
        </div>
        <div className="px-5 py-5">{children}</div>
      </div>
    </div>
  );
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="rounded border border-[#222124] bg-[#1C1B1E] px-4 py-8 text-center">
      <p className="font-mono text-xs uppercase tracking-widest text-[#77777D]">
        {label}
      </p>
    </div>
  );
}

export function ErrorBlock({ message }: { message: string }) {
  return (
    <div className="rounded border border-[#8E2638]/40 bg-[#8E2638]/10 px-4 py-3">
      <p className="font-mono text-xs uppercase tracking-wider text-[#E58A9B]">
        Request failed
      </p>
      <p className="mt-1 text-sm text-[#E8E3DC]">{message}</p>
    </div>
  );
}

export function EmptyBlock({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="rounded border border-dashed border-[#77777D]/30 bg-[#1C1B1E]/50 px-5 py-10 text-center">
      <p className="font-mono text-xs uppercase tracking-widest text-[#A6A1A0]">
        {title}
      </p>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#77777D]">
        {detail}
      </p>
    </div>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-[#77777D]">
      {children}
    </span>
  );
}

export const inputClass =
  "w-full rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2 text-sm text-[#F5F2EE] placeholder-[#77777D] focus:border-[#8E2638]/60 focus:outline-none disabled:opacity-50";

export const selectClass = `${inputClass} appearance-none`;
