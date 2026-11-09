"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  deleteIdea,
  fetchAssessments,
  fetchIdea,
  formatDateTime,
  messageFromError,
  updateIdea,
  type Idea,
} from "@/lib/api";
import AssessmentPanel from "./assessment-panel";
import ImprovementPanel from "./improvement-panel";

type IdeaState =
  | { phase: "loading" }
  | { phase: "loaded"; idea: Idea }
  | { phase: "not-found" }
  | { phase: "error"; message: string };

type FieldErrors = {
  title?: string;
  description?: string;
};

type Feedback = {
  tone: "success" | "error";
  message: string;
};

function parseIdeaId(value: string): number | null {
  const ideaId = Number(value);
  return Number.isInteger(ideaId) && ideaId > 0 ? ideaId : null;
}

async function loadIdeaState(
  ideaId: number,
  signal?: AbortSignal,
): Promise<IdeaState> {
  try {
    const idea = await fetchIdea(ideaId, signal);
    return { phase: "loaded", idea };
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }

    if (error instanceof ApiError && error.status === 404) {
      return { phase: "not-found" };
    }

    return { phase: "error", message: messageFromError(error) };
  }
}

export default function IdeaDetail({ ideaId }: { ideaId: string }) {
  const router = useRouter();
  const numericId = parseIdeaId(ideaId);
  const [ideaState, setIdeaState] = useState<IdeaState>(() =>
    numericId === null ? { phase: "not-found" } : { phase: "loading" },
  );
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [hasAssessment, setHasAssessment] = useState(false);

  useEffect(() => {
    if (numericId === null) {
      return;
    }

    const controller = new AbortController();

    loadIdeaState(numericId, controller.signal)
      .then((next) => setIdeaState(next))
      .catch(() => {});

    fetchAssessments(numericId, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setHasAssessment(items.length > 0);
        }
      })
      .catch(() => {});

    return () => controller.abort();
  }, [numericId]);

  useEffect(() => {
    if (!isDeleteOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isDeleting) {
        setIsDeleteOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isDeleteOpen, isDeleting]);

  const idea = ideaState.phase === "loaded" ? ideaState.idea : null;

  const retryLoad = () => {
    if (numericId === null) {
      return;
    }

    setIdeaState({ phase: "loading" });

    loadIdeaState(numericId)
      .then((next) => setIdeaState(next))
      .catch(() => {});
  };

  const beginEdit = () => {
    if (!idea) {
      return;
    }

    setEditTitle(idea.title);
    setEditDescription(idea.description);
    setFieldErrors({});
    setFeedback(null);
    setIsEditing(true);
  };

  const cancelEdit = () => {
    setIsEditing(false);
    setFieldErrors({});
    setFeedback(null);
  };

  const handleUpdate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!idea || isSaving) {
      return;
    }

    const cleanTitle = editTitle.trim();
    const cleanDescription = editDescription.trim();
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
      const updated = await updateIdea(idea.id, {
        title: cleanTitle,
        description: cleanDescription,
      });

      setIdeaState({ phase: "loaded", idea: updated });
      setIsEditing(false);
      setFeedback({ tone: "success", message: "Idea updated." });
    } catch (error) {
      setFeedback({
        tone: "error",
        message: `Could not update the idea: ${messageFromError(error)}`,
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!idea || isDeleting) {
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deleteIdea(idea.id);
      router.replace("/?deleted=1");
    } catch (error) {
      setDeleteError(messageFromError(error));
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-1 flex-col overflow-hidden bg-[#171719] text-[#F5F2EE] academy-grid">
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

      <main className="relative mx-auto w-full max-w-3xl flex-1 px-5 py-10 sm:px-8 sm:py-14">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-[#222124] pb-4">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-mono tracking-wider text-[#A6A1A0] transition-colors hover:text-[#F5F2EE] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#A52A42]"
          >
            <span aria-hidden="true">&larr;</span>
            RETURN TO ARCHIVE
          </Link>
          <div className="inline-flex items-center gap-2 rounded-full border border-[#8E2638]/30 bg-[#222124] px-3.5 py-1 text-xs font-mono text-[#E8E3DC]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#A52A42]" />
            DOSSIER // IDEA #{numericId}
          </div>
        </div>

        {ideaState.phase === "loading" && (
          <div
            aria-busy="true"
            className="rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-8 text-center backdrop-blur sm:p-10"
          >
            <div className="mx-auto h-4 w-4 rounded-full border-2 border-[#A52A42] border-t-transparent animate-spin mb-3" />
            <p className="text-xs font-mono text-[#A6A1A0]">MEMUAT DOSSIER IDEON…</p>
          </div>
        )}

        {ideaState.phase === "not-found" && (
          <section className="rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-8 shadow-xl backdrop-blur sm:p-10">
            <p className="text-xs font-mono uppercase tracking-[0.18em] text-[#E58A9B]">
              STATUS 404 // NOT FOUND
            </p>
            <h1 className="mt-3 text-2xl font-bold tracking-tight text-[#F5F2EE] sm:text-3xl font-mono">
              Dossier Not Found
            </h1>
            <p className="mt-3 max-w-md text-xs leading-6 text-[#A6A1A0]">
              Arsip ide ini tidak ditemukan atau telah dihapus dari sistem akademi.
            </p>
            <Link
              href="/"
              className="mt-6 inline-flex rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110"
            >
              Kembali ke Arsip
            </Link>
          </section>
        )}

        {ideaState.phase === "error" && (
          <section
            role="alert"
            className="rounded-2xl border border-rose-800/40 bg-rose-950/40 p-8 sm:p-10"
          >
            <h1 className="text-xl font-bold tracking-tight text-rose-300 font-mono">
              SISTEM GAGAL MEMUAT ARSIP
            </h1>
            <p className="mt-3 max-w-md text-xs leading-6 text-rose-200">
              {ideaState.message}
            </p>
            <button
              type="button"
              onClick={retryLoad}
              className="mt-6 rounded-lg border border-rose-800/50 bg-rose-900/30 px-4 py-2 text-xs font-mono text-rose-200 hover:bg-rose-900/50"
            >
              Coba Lagi
            </button>
          </section>
        )}

        {idea && isEditing && (
          <section
            aria-labelledby="edit-idea-heading"
            className="rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-6 shadow-xl backdrop-blur sm:p-8"
          >
            <div className="flex items-center justify-between border-b border-[#77777D]/15 pb-4">
              <h1
                id="edit-idea-heading"
                className="text-base font-semibold tracking-wide text-[#F5F2EE] uppercase font-mono"
              >
                UPDATE // EDIT DOSSIER
              </h1>
              <span className="text-[11px] font-mono text-[#E58A9B]">EDITING</span>
            </div>

            <form
              className="mt-6 space-y-4"
              onSubmit={handleUpdate}
              noValidate
              aria-busy={isSaving}
            >
              <div>
                <label
                  htmlFor="edit-idea-title"
                  className="text-xs font-medium uppercase tracking-wider text-[#E8E3DC]"
                >
                  Idea Title
                </label>
                <input
                  id="edit-idea-title"
                  name="title"
                  type="text"
                  value={editTitle}
                  onChange={(event) => {
                    setEditTitle(event.target.value);
                    if (fieldErrors.title) {
                      setFieldErrors((current) => ({
                        ...current,
                        title: undefined,
                      }));
                    }
                  }}
                  aria-invalid={Boolean(fieldErrors.title)}
                  className={`mt-1.5 w-full rounded-xl border bg-[#171719] px-3.5 py-2.5 text-sm text-[#F5F2EE] outline-none transition-colors placeholder:text-[#77777D] focus:border-[#A52A42] focus:ring-1 focus:ring-[#A52A42] ${
                    fieldErrors.title ? "border-rose-400" : "border-[#77777D]/25"
                  }`}
                />
                {fieldErrors.title && (
                  <p role="alert" className="mt-1.5 text-xs text-[#E58A9B] font-mono">
                    {fieldErrors.title}
                  </p>
                )}
              </div>

              <div>
                <label
                  htmlFor="edit-idea-description"
                  className="text-xs font-medium uppercase tracking-wider text-[#E8E3DC]"
                >
                  Description
                </label>
                <textarea
                  id="edit-idea-description"
                  name="description"
                  rows={8}
                  value={editDescription}
                  onChange={(event) => {
                    setEditDescription(event.target.value);
                    if (fieldErrors.description) {
                      setFieldErrors((current) => ({
                        ...current,
                        description: undefined,
                      }));
                    }
                  }}
                  aria-invalid={Boolean(fieldErrors.description)}
                  className={`mt-1.5 w-full resize-y rounded-xl border bg-[#171719] px-3.5 py-2.5 text-sm leading-6 text-[#F5F2EE] outline-none transition-colors placeholder:text-[#77777D] focus:border-[#A52A42] focus:ring-1 focus:ring-[#A52A42] ${
                    fieldErrors.description ? "border-rose-400" : "border-[#77777D]/25"
                  }`}
                />
                {fieldErrors.description && (
                  <p role="alert" className="mt-1.5 text-xs text-[#E58A9B] font-mono">
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

              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end pt-2">
                <button
                  type="button"
                  onClick={cancelEdit}
                  disabled={isSaving}
                  className="rounded-xl border border-[#77777D]/25 bg-[#171719] px-4 py-2 text-xs font-medium text-[#E8E3DC] transition-colors hover:bg-[#222124] disabled:opacity-50"
                >
                  BATAL
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 transition-all hover:brightness-110 disabled:opacity-50"
                >
                  {isSaving ? "SAVING CHANGES…" : "SAVE CHANGES"}
                </button>
              </div>
            </form>
          </section>
        )}

        {idea && !isEditing && (
          <>
            <article className="relative rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-6 shadow-xl backdrop-blur sm:p-8">
              <div className="absolute top-0 left-6 right-6 h-[2px] bg-gradient-to-r from-transparent via-[#8E2638] to-transparent" />

              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between border-b border-[#77777D]/15 pb-5">
                <div className="ribbon-accent pl-4">
                  <span className="text-[10px] font-mono tracking-widest text-[#E58A9B] uppercase font-semibold">
                    ORIGINAL RECORD // DOSSIER BASE
                  </span>
                  <h1 className="mt-1 min-w-0 break-words text-2xl font-bold tracking-tight text-[#F5F2EE] sm:text-3xl">
                    {idea.title}
                  </h1>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={beginEdit}
                    className="rounded-lg border border-[#77777D]/25 bg-[#171719] px-3.5 py-1.5 text-xs font-mono font-medium text-[#E8E3DC] transition-colors hover:border-[#8E2638]"
                  >
                    EDIT
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                      setIsDeleteOpen(true);
                    }}
                    className="rounded-lg border border-rose-800/40 bg-rose-950/20 px-3.5 py-1.5 text-xs font-mono font-medium text-rose-300 transition-colors hover:bg-rose-950/40"
                  >
                    DELETE
                  </button>
                </div>
              </div>

              {feedback && (
                <p
                  role={feedback.tone === "error" ? "alert" : "status"}
                  className={`mt-4 rounded-xl px-3.5 py-2.5 text-xs font-mono ${
                    feedback.tone === "error"
                      ? "bg-rose-950/60 text-rose-300 border border-rose-800/40"
                      : "bg-[#8E2638]/20 text-[#F5F2EE] border border-[#8E2638]/40"
                  }`}
                >
                  {feedback.message}
                </p>
              )}

              <p className="mt-6 whitespace-pre-line break-words text-sm leading-7 text-[#E8E3DC]">
                {idea.description}
              </p>

              <dl className="mt-8 grid gap-4 border-t border-[#77777D]/15 pt-5 sm:grid-cols-2">
                <div>
                  <dt className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
                    RECORDED DATE
                  </dt>
                  <dd className="mt-1 text-xs font-mono text-[#A6A1A0]">
                    <time dateTime={idea.created_at}>
                      {formatDateTime(idea.created_at)}
                    </time>
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
                    LAST UPDATED
                  </dt>
                  <dd className="mt-1 text-xs font-mono text-[#A6A1A0]">
                    <time dateTime={idea.updated_at}>
                      {formatDateTime(idea.updated_at)}
                    </time>
                  </dd>
                </div>
              </dl>
            </article>

            <ImprovementPanel
              key={`improvement-${idea.id}`}
              idea={idea}
              hasAssessment={hasAssessment}
              onSessionUpdated={() => {
                if (numericId !== null) {
                  fetchAssessments(numericId)
                    .then((items) => setHasAssessment(items.length > 0))
                    .catch(() => {});
                }
              }}
            />

            <AssessmentPanel
              key={idea.id}
              idea={idea}
              onAssessmentCompleted={() => setHasAssessment(true)}
            />
          </>
        )}
      </main>

      {isDeleteOpen && idea && (
        <div
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !isDeleting) {
              setIsDeleteOpen(false);
            }
          }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-idea-heading"
            aria-describedby="delete-idea-description"
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-rose-900/40 bg-[#171719] p-6 shadow-2xl sm:p-7"
          >
            <div className="flex items-center gap-2 text-[#E58A9B] font-mono text-xs uppercase tracking-wider mb-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[#E58A9B] animate-pulse" />
              CONFIRM ARCHIVE PURGE
            </div>
            <h2
              id="delete-idea-heading"
              className="text-lg font-bold tracking-tight text-[#F5F2EE]"
            >
              Hapus Arsip Ide Ini?
            </h2>
            <p
              id="delete-idea-description"
              className="mt-2 text-xs leading-5 text-[#A6A1A0]"
            >
              Tindakan ini akan menghapus permanen &ldquo;{idea.title}&rdquo; beserta seluruh riwayat asesmen dan revisi terkait. Tindakan ini tidak dapat dibatalkan.
            </p>

            {deleteError && (
              <p
                role="alert"
                className="mt-4 rounded-xl bg-rose-950/60 p-2.5 text-xs text-rose-300 border border-rose-800/40"
              >
                {deleteError}
              </p>
            )}

            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setIsDeleteOpen(false)}
                disabled={isDeleting}
                className="rounded-xl border border-[#77777D]/25 bg-[#222124] px-4 py-2 text-xs font-mono font-medium text-[#E8E3DC] hover:bg-[#2a292d] disabled:opacity-50"
              >
                BATALKAN
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={isDeleting}
                className="rounded-xl bg-rose-800 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider text-white hover:bg-rose-700 disabled:opacity-50"
              >
                {isDeleting ? "PURGING RECORD…" : "HAPUS DOSSIER"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
