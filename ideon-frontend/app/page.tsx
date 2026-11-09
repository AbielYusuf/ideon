"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  apiUrl,
  configurationError,
  createIdea,
  fetchIdeas,
  formatDate,
  messageFromError,
  type Idea,
} from "@/lib/api";

type HealthResponse = {
  status: string;
  application: string;
  message: string;
};

type ConnectionState =
  | { phase: "loading" }
  | { phase: "connected"; health: HealthResponse }
  | { phase: "disconnected"; error: string };

type FieldErrors = {
  title?: string;
  description?: string;
};

type Feedback = {
  tone: "success" | "error";
  message: string;
};

async function fetchConnection(signal?: AbortSignal): Promise<ConnectionState> {
  if (!apiUrl) {
    return { phase: "disconnected", error: configurationError! };
  }

  try {
    const response = await fetch(`${apiUrl}/api/health`, {
      cache: "no-store",
      signal,
    });

    if (!response.ok) {
      throw new Error(`The backend returned HTTP ${response.status}.`);
    }

    const health = (await response.json()) as HealthResponse;

    if (health.status !== "ok") {
      throw new Error("The backend health check did not return an OK status.");
    }

    return { phase: "connected", health };
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }

    return { phase: "disconnected", error: messageFromError(error) };
  }
}

function DeletedNotice() {
  const searchParams = useSearchParams();

  if (searchParams.get("deleted") !== "1") {
    return null;
  }

  return (
    <div
      role="status"
      className="mb-8 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-sm text-emerald-800"
    >
      <p>Idea deleted successfully.</p>
      <Link
        href="/"
        className="font-medium underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-900"
      >
        Dismiss
      </Link>
    </div>
  );
}

export default function Home() {
  const [connection, setConnection] = useState<ConnectionState>(() =>
    configurationError
      ? { phase: "disconnected", error: configurationError }
      : { phase: "loading" },
  );
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [ideasLoading, setIdeasLoading] = useState(true);
  const [ideasError, setIdeasError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchConnection(controller.signal)
      .then((next) => setConnection(next))
      .catch(() => {});

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    fetchIdeas(controller.signal)
      .then((next) => {
        setIdeas(next);
        setIdeasError(null);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setIdeasError(messageFromError(error));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIdeasLoading(false);
        }
      });

    return () => controller.abort();
  }, []);

  const retryConnection = () => {
    if (!apiUrl) {
      return;
    }

    setConnection({ phase: "loading" });

    fetchConnection()
      .then((next) => setConnection(next))
      .catch(() => {});
  };

  const reloadIdeas = () => {
    setIdeasLoading(true);
    setIdeasError(null);

    fetchIdeas()
      .then((next) => {
        setIdeas(next);
        setIdeasError(null);
      })
      .catch((error) => setIdeasError(messageFromError(error)))
      .finally(() => setIdeasLoading(false));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isSaving) {
      return;
    }

    const cleanTitle = title.trim();
    const cleanDescription = description.trim();
    const nextErrors: FieldErrors = {};

    if (!cleanTitle) {
      nextErrors.title = "Enter a title for your idea.";
    }

    if (!cleanDescription) {
      nextErrors.description = "Add a short description.";
    }

    setFieldErrors(nextErrors);

    if (Object.keys(nextErrors).length > 0) {
      setFeedback(null);
      return;
    }

    setIsSaving(true);
    setFeedback(null);

    try {
      const created = await createIdea({
        title: cleanTitle,
        description: cleanDescription,
      });

      setTitle("");
      setDescription("");
      setFieldErrors({});
      setFeedback({ tone: "success", message: "Idea saved." });
      setIdeas((current) => [created, ...current]);

      try {
        const refreshed = await fetchIdeas();
        setIdeas(refreshed);
        setIdeasError(null);
      } catch (error) {
        setIdeasError(
          `Idea saved, but the list could not be refreshed: ${messageFromError(error)}`,
        );
      }
    } catch (error) {
      setFeedback({
        tone: "error",
        message: `Could not save the idea: ${messageFromError(error)}`,
      });
    } finally {
      setIsSaving(false);
    }
  };

  const isConnected = connection.phase === "connected";
  const isChecking = connection.phase === "loading";
  const statusLabel = isChecking
    ? "Checking"
    : isConnected
      ? "Connected"
      : "Disconnected";
  const statusDetail = isChecking
    ? "Checking the Ideon API…"
    : isConnected
      ? connection.health.message
      : connection.error;

  return (
    <div className="relative flex min-h-screen flex-1 flex-col overflow-hidden bg-[#171719] text-[#F5F2EE] academy-grid">
      {/* Academy Dark Atmosphere Background Ornaments */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-40 -right-32 h-[32rem] w-[32rem] rounded-full bg-[#8E2638]/10 blur-[120px]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-48 -left-32 h-[32rem] w-[32rem] rounded-full bg-[#222124] blur-[100px]"
      />

      {/* Top Academic Measurement Accent Bar */}
      <div className="w-full ruler-ticks opacity-40 border-b border-[#222124]" />

      <main className="relative mx-auto w-full max-w-5xl flex-1 px-5 py-10 sm:px-8 sm:py-14">
        <Suspense fallback={null}>
          <DeletedNotice />
        </Suspense>

        {/* Japanese Academy Identification Header */}
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-[#222124] pb-4">
          <div className="inline-flex items-center gap-2.5 rounded-full border border-[#8E2638]/30 bg-[#222124]/90 px-3.5 py-1 text-xs font-medium tracking-wider text-[#E8E3DC] backdrop-blur shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-[#A52A42] animate-pulse" />
            <span className="text-[#A6A1A0]">ARCHIVE PROTOCOL</span> · 01 ACADEMY WORKSPACE
          </div>
          <div className="hidden sm:flex items-center gap-4 text-xs font-mono text-[#77777D]">
            <span>CLASS: REFINEMENT</span>
            <span>SYSTEM: ONLINE</span>
          </div>
        </div>

        <header className="flex flex-col gap-7 sm:flex-row sm:items-start sm:justify-between">
          <div className="ribbon-accent pl-5">
            <div className="flex items-center gap-3">
              <h1 className="text-4xl font-bold tracking-[0.2em] text-[#F5F2EE] sm:text-5xl font-mono">
                IDEON
              </h1>
              <span className="rounded border border-[#8E2638]/40 bg-[#8E2638]/20 px-2 py-0.5 text-[10px] font-mono tracking-widest text-[#E58A9B]">
                IDEA ARCHIVE
              </span>
            </div>
            <p className="mt-3 text-xl font-medium tracking-tight text-[#E8E3DC] sm:text-2xl">
              Precision Idea Refinement & Assessment
            </p>
            <p className="mt-2 max-w-xl text-sm leading-6 text-[#A6A1A0]">
              Catat ide bernilai tinggi, evaluasi dengan rubrik standar akademi, dan sempurnakan secara terukur bersama AI.
            </p>
          </div>

          <aside
            aria-label="Backend connection status"
            className="w-full shrink-0 rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-4 shadow-xl backdrop-blur sm:w-72"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
                SYS · DIAGNOSTIC
              </p>
              <span
                aria-live="polite"
                className={`inline-flex items-center gap-2 rounded-full px-2.5 py-0.5 text-xs font-mono ${
                  isChecking
                    ? "bg-[#77777D]/10 text-[#E8E3DC]"
                    : isConnected
                      ? "bg-[#8E2638]/20 text-[#F5F2EE] border border-[#8E2638]/40"
                      : "bg-rose-950/40 text-rose-300 border border-rose-800/40"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    isChecking
                      ? "bg-[#A6A1A0]"
                      : isConnected
                        ? "bg-[#A52A42]"
                        : "bg-rose-500"
                  }`}
                />
                {statusLabel}
              </span>
            </div>
            <p className="mt-2.5 break-words font-mono text-xs leading-5 text-[#A6A1A0]">
              {statusDetail}
            </p>
            {connection.phase === "disconnected" && (
              <button
                type="button"
                onClick={retryConnection}
                className="mt-3 rounded-lg border border-[#8E2638]/40 bg-[#8E2638]/20 px-3 py-1.5 text-xs font-medium text-[#F5F2EE] transition-colors hover:bg-[#8E2638]/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#A52A42]"
              >
                Re-connect
              </button>
            )}
          </aside>
        </header>

        <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          {/* New Idea Form Card */}
          <section
            aria-labelledby="new-idea-heading"
            className="relative rounded-2xl border border-[#77777D]/20 bg-[#222124]/70 p-6 shadow-xl backdrop-blur sm:p-7"
          >
            {/* Top Border Red Accent */}
            <div className="absolute top-0 left-6 right-6 h-[2px] bg-gradient-to-r from-transparent via-[#8E2638] to-transparent" />

            <div className="flex items-center justify-between">
              <h2
                id="new-idea-heading"
                className="text-base font-semibold tracking-wide text-[#F5F2EE] uppercase font-mono"
              >
                ENTRY // 01 NEW PROPOSAL
              </h2>
              <span className="text-[11px] font-mono text-[#E58A9B]">ACADEMY PROTOCOL</span>
            </div>
            <p className="mt-1 text-xs leading-5 text-[#A6A1A0]">
              Daftarkan judul dan deskripsi ide untuk mulai dianalisis.
            </p>

            <form
              className="mt-6 space-y-4"
              onSubmit={handleSubmit}
              noValidate
              aria-busy={isSaving}
            >
              <div>
                <label
                  htmlFor="idea-title"
                  className="text-xs font-medium uppercase tracking-wider text-[#E8E3DC]"
                >
                  Idea Title
                </label>
                <input
                  id="idea-title"
                  name="title"
                  type="text"
                  value={title}
                  onChange={(event) => {
                    setTitle(event.target.value);
                    if (fieldErrors.title) {
                      setFieldErrors((current) => ({
                        ...current,
                        title: undefined,
                      }));
                    }
                  }}
                  placeholder="e.g. Autonomous Campus Navigation"
                  aria-invalid={Boolean(fieldErrors.title)}
                  aria-describedby={
                    fieldErrors.title ? "idea-title-error" : undefined
                  }
                  className={`mt-1.5 w-full rounded-xl border bg-[#171719] px-3.5 py-2.5 text-sm text-[#F5F2EE] outline-none transition-colors placeholder:text-[#77777D] focus:border-[#A52A42] focus:ring-1 focus:ring-[#A52A42] ${
                    fieldErrors.title
                      ? "border-rose-400"
                      : "border-[#77777D]/25"
                  }`}
                />
                {fieldErrors.title && (
                  <p
                    id="idea-title-error"
                    role="alert"
                    className="mt-1.5 text-xs text-[#E58A9B] font-mono"
                  >
                    {fieldErrors.title}
                  </p>
                )}
              </div>

              <div>
                <label
                  htmlFor="idea-description"
                  className="text-xs font-medium uppercase tracking-wider text-[#E8E3DC]"
                >
                  Proposal Details
                </label>
                <textarea
                  id="idea-description"
                  name="description"
                  rows={5}
                  value={description}
                  onChange={(event) => {
                    setDescription(event.target.value);
                    if (fieldErrors.description) {
                      setFieldErrors((current) => ({
                        ...current,
                        description: undefined,
                      }));
                    }
                  }}
                  placeholder="Jelaskan tujuan, ruang lingkup, dan konteks penting dari ide ini..."
                  aria-invalid={Boolean(fieldErrors.description)}
                  aria-describedby={
                    fieldErrors.description
                      ? "idea-description-error"
                      : undefined
                  }
                  className={`mt-1.5 w-full resize-y rounded-xl border bg-[#171719] px-3.5 py-2.5 text-sm leading-6 text-[#F5F2EE] outline-none transition-colors placeholder:text-[#77777D] focus:border-[#A52A42] focus:ring-1 focus:ring-[#A52A42] ${
                    fieldErrors.description
                      ? "border-rose-400"
                      : "border-[#77777D]/25"
                  }`}
                />
                {fieldErrors.description && (
                  <p
                    id="idea-description-error"
                    role="alert"
                    className="mt-1.5 text-xs text-[#E58A9B] font-mono"
                  >
                    {fieldErrors.description}
                  </p>
                )}
              </div>

              {feedback && (
                <p
                  role={feedback.tone === "error" ? "alert" : "status"}
                  className={`rounded-xl px-3.5 py-2.5 text-xs font-mono ${
                    feedback.tone === "error"
                      ? "bg-rose-950/60 text-rose-300 border border-rose-800/40"
                      : "bg-[#8E2638]/20 text-[#F5F2EE] border border-[#8E2638]/40"
                  }`}
                >
                  {feedback.message}
                </p>
              )}

              <button
                type="submit"
                disabled={isSaving}
                className="w-full rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 transition-all hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#A52A42] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? "REGISTERING RECORD…" : "SUBMIT PROPOSAL RECORD"}
              </button>
            </form>
          </section>

          {/* Ideas Archive List */}
          <section
            aria-labelledby="ideas-heading"
            className="rounded-2xl border border-[#77777D]/20 bg-[#222124]/70 p-6 shadow-xl backdrop-blur sm:p-7"
          >
            <div className="flex items-start justify-between gap-4 border-b border-[#77777D]/15 pb-4">
              <div>
                <h2
                  id="ideas-heading"
                  className="text-base font-semibold tracking-wide text-[#F5F2EE] uppercase font-mono"
                >
                  ARCHIVE // RECORDED PROPOSALS
                </h2>
                <p className="mt-1 text-xs leading-5 text-[#A6A1A0]">
                  Pilih arsip ide untuk melihat detail, asesmen, atau perbaikan iterasi.
                </p>
              </div>
              {!ideasLoading && ideas.length > 0 && (
                <span className="shrink-0 rounded-full border border-[#8E2638]/40 bg-[#8E2638]/15 px-2.5 py-0.5 text-xs font-mono font-medium text-[#E8E3DC]">
                  {ideas.length} RECS
                </span>
              )}
            </div>

            <div className="mt-5">
              {ideasLoading && (
                <div
                  aria-busy="true"
                  className="rounded-xl border border-dashed border-[#77777D]/25 bg-[#171719]/40 px-6 py-10 text-center"
                >
                  <div className="mx-auto h-4 w-4 rounded-full border-2 border-[#A52A42] border-t-transparent animate-spin mb-3" />
                  <p className="text-xs font-mono text-[#A6A1A0]">MEMUAT ARSIP IDEON...</p>
                </div>
              )}

              {!ideasLoading && ideasError && ideas.length === 0 && (
                <div
                  role="alert"
                  className="rounded-xl border border-rose-800/40 bg-rose-950/40 p-4"
                >
                  <p className="text-xs font-semibold text-rose-300 font-mono">
                    ERROR: GAGAL MEMUAT ARSIP
                  </p>
                  <p className="mt-1 text-xs leading-5 text-rose-200">
                    {ideasError}
                  </p>
                  <button
                    type="button"
                    onClick={reloadIdeas}
                    className="mt-3 rounded-lg border border-rose-800/50 bg-rose-900/30 px-3 py-1 text-xs font-mono text-rose-200 hover:bg-rose-900/50"
                  >
                    Retry
                  </button>
                </div>
              )}

              {!ideasLoading && !ideasError && ideas.length === 0 && (
                <div className="rounded-xl border border-dashed border-[#77777D]/25 bg-[#171719]/40 px-6 py-10 text-center">
                  <p className="text-sm font-medium text-[#E8E3DC]">
                    Arsip Masih Kosong
                  </p>
                  <p className="mx-auto mt-1 max-w-xs text-xs leading-5 text-[#77777D]">
                    Gunakan formulir untuk mendaftarkan usulan ide pertama Anda ke dalam sistem akademi.
                  </p>
                </div>
              )}

              {!ideasLoading && ideas.length > 0 && (
                <>
                  {ideasError && (
                    <div
                      role="alert"
                      className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-rose-950/60 p-2.5 text-xs text-rose-300 border border-rose-800/40"
                    >
                      <p>{ideasError}</p>
                      <button
                        type="button"
                        onClick={reloadIdeas}
                        className="underline"
                      >
                        Refresh
                      </button>
                    </div>
                  )}

                  <ul className="space-y-3">
                    {ideas.map((idea, idx) => (
                      <li key={idea.id}>
                        <article>
                          <Link
                            href={`/ideas/${idea.id}`}
                            className="group block rounded-xl border border-[#77777D]/20 bg-[#171719]/80 p-4 transition-all hover:border-[#A52A42] hover:bg-[#222124] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#A52A42] sm:p-4.5"
                          >
                            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs font-semibold text-[#E58A9B]">
                                  #{String(idx + 1).padStart(2, "0")}
                                </span>
                                <h3 className="text-sm font-semibold text-[#F5F2EE] group-hover:text-[#E8E3DC]">
                                  {idea.title}
                                </h3>
                              </div>
                              <time
                                dateTime={idea.created_at}
                                className="shrink-0 font-mono text-[11px] text-[#77777D]"
                              >
                                {formatDate(idea.created_at)}
                              </time>
                            </div>
                            <p className="mt-2 line-clamp-2 text-xs leading-5 text-[#A6A1A0]">
                              {idea.description}
                            </p>
                            <div className="mt-3 flex items-center justify-between border-t border-[#77777D]/10 pt-2 text-[11px] font-mono text-[#77777D]">
                              <span>INSPECT RECORD →</span>
                              <span className="text-[#E58A9B] opacity-0 group-hover:opacity-100 transition-opacity font-semibold">● OPEN</span>
                            </div>
                          </Link>
                        </article>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
