"use client";

import { useEffect, useRef, useState } from "react";

import {
  actOnImprovementProposal,
  fetchActiveImprovementSession,
  formatDateTime,
  messageFromError,
  requestImprovementProposal,
  startImprovementSession,
  stopImprovementSession,
  type Idea,
  type ImprovementProposal,
  type ImprovementSessionDetail,
  type ScoreComparison,
} from "@/lib/api";

function scoreBadgeClass(classification: string): string {
  switch (classification) {
    case "Strong":
      return "border border-emerald-500/40 bg-emerald-950/40 text-emerald-300";
    case "Promising":
      return "border border-sky-500/40 bg-sky-950/40 text-sky-300";
    case "Needs Improvement":
      return "border border-[#8E2638]/50 bg-[#8E2638]/20 text-[#E8E3DC]";
    case "Weak":
      return "border border-rose-800/40 bg-rose-950/40 text-rose-300";
    default:
      return "border border-[#77777D]/30 bg-[#222124] text-[#A6A1A0]";
  }
}

export default function ImprovementPanel({
  idea,
  hasAssessment,
  onSessionUpdated,
}: {
  idea: Idea;
  hasAssessment: boolean;
  onSessionUpdated?: () => void;
}) {
  const [sessionDetail, setSessionDetail] =
    useState<ImprovementSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [latestComparison, setLatestComparison] =
    useState<ScoreComparison | null>(null);
  const [selectedRevisionTab, setSelectedRevisionTab] = useState<number | null>(
    null,
  );
  const requestRef = useRef<AbortController | null>(null);

  const loadActiveSession = async (signal?: AbortSignal) => {
    try {
      const detail = await fetchActiveImprovementSession(idea.id, signal);
      if (!signal?.aborted) {
        setSessionDetail(detail);
      }
    } catch (err) {
      if (!signal?.aborted) {
        setError(messageFromError(err));
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    loadActiveSession(controller.signal);
    return () => controller.abort();
  }, [idea.id]);

  const handleStartSession = async () => {
    setIsBusy(true);
    setBusyMessage("Memulai sesi perbaikan...");
    setError(null);
    setLatestComparison(null);

    try {
      await startImprovementSession(idea.id);
      await loadActiveSession();
      if (onSessionUpdated) onSessionUpdated();
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setIsBusy(false);
    }
  };

  const handleRequestProposal = async () => {
    if (!sessionDetail) return;
    setIsBusy(true);
    setBusyMessage("AI sedang merumuskan proposal perbaikan...");
    setError(null);
    setLatestComparison(null);

    try {
      await requestImprovementProposal(idea.id, sessionDetail.session.id);
      await loadActiveSession();
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setIsBusy(false);
    }
  };

  const handleProposalAction = async (
    proposal: ImprovementProposal,
    action: "accept" | "reject" | "regenerate",
  ) => {
    if (!sessionDetail) return;

    if (
      action === "accept" &&
      !window.confirm(
        "Apakah Anda yakin ingin menyetujui proposal ini dan melakukan assessment ulang?",
      )
    ) {
      return;
    }

    setIsBusy(true);
    setBusyMessage(
      action === "accept"
        ? "AI sedang menilai revisi baru..."
        : action === "regenerate"
          ? "AI sedang membuat alternatif proposal..."
          : "Menolak proposal...",
    );
    setError(null);

    try {
      const res = await actOnImprovementProposal(
        idea.id,
        sessionDetail.session.id,
        proposal.id,
        action,
      );

      if (res.action === "accept" && res.comparison) {
        setLatestComparison(res.comparison);
      }

      await loadActiveSession();
      if (onSessionUpdated) onSessionUpdated();
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setIsBusy(false);
    }
  };

  const handleStopSession = async () => {
    if (!sessionDetail) return;
    if (
      !window.confirm(
        "Hentikan sesi improvement ini? Sesi yang dihentikan tidak dapat menerima revisi lagi.",
      )
    ) {
      return;
    }

    setIsBusy(true);
    setBusyMessage("Menghentikan sesi...");
    setError(null);

    try {
      await stopImprovementSession(idea.id, sessionDetail.session.id);
      await loadActiveSession();
      if (onSessionUpdated) onSessionUpdated();
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setIsBusy(false);
    }
  };

  if (!hasAssessment) {
    return (
      <section className="mt-6 rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-6 shadow-xl backdrop-blur sm:p-7">
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-[#8E2638]/40 bg-[#8E2638]/20 text-xs font-mono font-bold text-[#E58A9B]">
            !
          </span>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#F5F2EE] font-mono">
              MANUAL IMPROVEMENT LOOP // ITERATION PROTOCOL
            </h3>
            <p className="mt-0.5 text-xs text-[#A6A1A0]">
              Selesaikan asesmen awal pada arsip ini untuk membuka protokol perbaikan iteratif.
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (loading) {
    return (
      <div className="mt-6 rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-6 text-center text-xs font-mono text-[#A6A1A0]">
        MEMERIKSA SESI IMPROVEMENT...
      </div>
    );
  }

  const session = sessionDetail?.session;
  const currentText = sessionDetail?.current_text;
  const currentAssessment = sessionDetail?.current_assessment;
  const pendingProposal = sessionDetail?.pending_proposal;
  const revisions = sessionDetail?.revisions ?? [];

  return (
    <section className="mt-6 rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-6 shadow-xl backdrop-blur sm:p-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#77777D]/15 pb-5">
        <div className="ribbon-accent pl-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#8E2638]/30 bg-[#8E2638]/15 px-3 py-0.5 text-[10px] font-mono font-medium text-[#E8E3DC]">
            <span className="h-1.5 w-1.5 rounded-full bg-[#A52A42]" />
            PHASE 05 · ITERATIVE REFINEMENT
          </div>
          <h2 className="mt-2 text-lg font-bold tracking-tight text-[#F5F2EE] font-mono">
            MANUAL IMPROVEMENT LOOP
          </h2>
          <p className="mt-1 text-xs text-[#A6A1A0]">
            Sempurnakan ide secara terukur berdasarkan catatan kelemahan asesmen (maksimal 5 revisi disetujui).
          </p>
        </div>

        {/* Counter and Stop */}
        {session && session.status === "active" && (
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="rounded-lg border border-[#8E2638]/40 bg-[#171719] px-3 py-1.5 text-xs font-mono font-semibold text-[#E8E3DC]">
              REVISI: {session.accepted_revision_count} / 5
            </div>
            <button
              type="button"
              onClick={handleStopSession}
              disabled={isBusy}
              className="rounded-lg border border-rose-800/40 bg-rose-950/20 px-3 py-1.5 text-xs font-mono text-rose-300 hover:bg-rose-950/40 disabled:opacity-50"
            >
              HENTIKAN SESI
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-rose-800/40 bg-rose-950/60 p-3 text-xs text-rose-300 font-mono">
          {error}
        </div>
      )}

      {isBusy && (
        <div className="mt-4 flex items-center gap-3 rounded-xl border border-[#77777D]/20 bg-[#171719]/80 px-4 py-3 text-xs text-[#E8E3DC] font-mono">
          <span className="h-2 w-2 animate-ping rounded-full bg-[#A52A42]" />
          <span>{busyMessage.toUpperCase()}</span>
        </div>
      )}

      {/* No Active Session State */}
      {!session && (
        <div className="mt-6 rounded-xl border border-dashed border-[#77777D]/25 bg-[#171719]/40 p-6 text-center">
          <h3 className="text-xs font-semibold text-[#F5F2EE] font-mono uppercase tracking-wider">
            Belum Ada Sesi Improvement yang Aktif
          </h3>
          <p className="mt-1 text-xs text-[#A6A1A0]">
            Mulai sesi untuk meminta AI merumuskan proposal perbaikan terarah sesuai hasil evaluasi terakhir.
          </p>
          <button
            type="button"
            onClick={handleStartSession}
            disabled={isBusy}
            className="mt-4 inline-flex items-center rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110 disabled:opacity-50"
          >
            Mulai Sesi Improvement
          </button>
        </div>
      )}

      {/* Active Session Content */}
      {session && (
        <div className="mt-6 space-y-6">
          {/* Status info if completed */}
          {session.status === "completed" && (
            <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-4 text-xs font-mono text-emerald-200">
              ✓ SESI TELAH SELESAI ({session.accepted_revision_count} revisi diterima).
            </div>
          )}

          {/* Score Comparison Banner */}
          {latestComparison && (
            <div className="rounded-xl border border-[#8E2638]/40 bg-[#8E2638]/10 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h4 className="text-xs font-semibold text-[#F5F2EE] font-mono uppercase tracking-wider">
                  Delta Perbandingan Skor Revisi
                </h4>
                <div className="flex items-center gap-2 font-mono">
                  <span className="text-xs text-[#77777D]">
                    {latestComparison.old_final_score} →
                  </span>
                  <span className="text-sm font-bold text-[#E8E3DC]">
                    {latestComparison.new_final_score}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                      latestComparison.final_score_delta >= 0
                        ? "bg-emerald-950/80 text-emerald-300 border border-emerald-600/40"
                        : "bg-rose-950/80 text-rose-300 border border-rose-600/40"
                    }`}
                  >
                    {latestComparison.final_score_delta >= 0 ? "+" : ""}
                    {latestComparison.final_score_delta} pts
                  </span>
                </div>
              </div>

              <div className="mt-3 grid gap-2 sm:grid-cols-5">
                {latestComparison.criteria_deltas.map((c) => (
                  <div
                    key={c.criterion}
                    className="rounded-lg border border-[#77777D]/20 bg-[#171719]/80 p-2.5 text-xs font-mono"
                  >
                    <p className="text-[11px] text-[#A6A1A0] truncate">
                      {c.criterion}
                    </p>
                    <div className="mt-1 flex items-baseline justify-between">
                      <span className="font-semibold text-[#F5F2EE]">
                        {c.new_score}
                      </span>
                      <span
                        className={
                          c.delta >= 0
                            ? "font-semibold text-emerald-400"
                            : "font-semibold text-rose-400"
                        }
                      >
                        {c.delta >= 0 ? `+${c.delta}` : c.delta}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Current State vs Proposal Side-by-Side */}
          {session.status === "active" && (
            <div>
              {!pendingProposal ? (
                <div className="rounded-xl border border-[#77777D]/20 bg-[#171719]/80 p-6 text-center">
                  <h4 className="text-xs font-semibold text-[#F5F2EE] font-mono uppercase tracking-wider">
                    Siap untuk iterasi berikutnya (
                    {session.accepted_revision_count === 0
                      ? "Basis: Ide Orisinal"
                      : `Basis: Revisi #${session.accepted_revision_count}`}
                    )
                  </h4>
                  <p className="mt-1 text-xs text-[#A6A1A0]">
                    AI akan menggunakan teks terkini dan temuan asesmen untuk menyusun proposal perbaikan terarah.
                  </p>
                  <button
                    type="button"
                    onClick={handleRequestProposal}
                    disabled={isBusy}
                    className="mt-4 rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110 disabled:opacity-50"
                  >
                    Minta Proposal Perbaikan AI
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid gap-4 lg:grid-cols-2">
                    {/* Before (Current Text) */}
                    <div className="rounded-xl border border-[#77777D]/20 bg-[#171719]/80 p-5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
                          {session.accepted_revision_count === 0
                            ? "Sebelumnya (Ide Orisinal)"
                            : `Sebelumnya (Revisi #${session.accepted_revision_count})`}
                        </span>
                        {currentAssessment && (
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-mono ${scoreBadgeClass(
                              currentAssessment.classification,
                            )}`}
                          >
                            Skor: {currentAssessment.final_score}
                          </span>
                        )}
                      </div>
                      <h4 className="mt-2 text-sm font-semibold text-[#F5F2EE]">
                        {currentText?.title}
                      </h4>
                      <p className="mt-2 whitespace-pre-line text-xs leading-5 text-[#A6A1A0]">
                        {currentText?.description}
                      </p>
                    </div>

                    {/* After (Proposed Text) */}
                    <div className="rounded-xl border border-[#8E2638]/40 bg-[#8E2638]/10 p-5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#E58A9B] font-semibold">
                          Usulan Perbaikan (Percobaan #{pendingProposal.proposal_attempt})
                        </span>
                        <span className="rounded-full border border-[#8E2638]/40 bg-[#8E2638]/20 px-2 py-0.5 text-[10px] font-mono text-[#E58A9B]">
                          PENDING
                        </span>
                      </div>
                      <h4 className="mt-2 text-sm font-semibold text-[#F5F2EE]">
                        {pendingProposal.proposed_title}
                      </h4>
                      <p className="mt-2 whitespace-pre-line text-xs leading-5 text-[#E8E3DC]">
                        {pendingProposal.proposed_description}
                      </p>

                      <div className="mt-4 border-t border-[#8E2638]/20 pt-3">
                        <p className="text-[10px] font-mono uppercase tracking-wider text-[#E58A9B] font-semibold">
                          Alasan Perubahan (Rationale):
                        </p>
                        <p className="mt-1 text-xs text-[#A6A1A0]">
                          {pendingProposal.rationale}
                        </p>

                        {pendingProposal.key_changes.length > 0 && (
                          <ul className="mt-2 space-y-1 text-xs text-[#A6A1A0]">
                            {pendingProposal.key_changes.map((change, idx) => (
                              <li key={idx} className="flex gap-2">
                                <span className="text-[#E58A9B]">▸</span>
                                <span>{change}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div className="flex flex-wrap items-center justify-end gap-3 pt-1">
                    <button
                      type="button"
                      onClick={() =>
                        handleProposalAction(pendingProposal, "reject")
                      }
                      disabled={isBusy}
                      className="rounded-xl border border-[#77777D]/25 bg-[#171719] px-3.5 py-2 text-xs font-mono font-medium text-[#E8E3DC] hover:bg-[#222124] disabled:opacity-50"
                    >
                      TOLAK PROPOSAL
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleProposalAction(pendingProposal, "regenerate")
                      }
                      disabled={isBusy}
                      className="rounded-xl border border-[#77777D]/25 bg-[#171719] px-3.5 py-2 text-xs font-mono font-medium text-[#E8E3DC] hover:bg-[#222124] disabled:opacity-50"
                    >
                      REGENERATE (OPSI LAIN)
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleProposalAction(pendingProposal, "accept")
                      }
                      disabled={isBusy}
                      className="rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110 disabled:opacity-50"
                    >
                      TERIMA REVISI & NILAI ULANG
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Revisions History Tab */}
          {revisions.length > 0 && (
            <div className="mt-8 border-t border-[#77777D]/15 pt-5">
              <h4 className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
                Riwayat Revisi Terarsip ({revisions.length} revisi)
              </h4>
              <div className="mt-3 flex flex-wrap gap-2">
                {revisions.map((rev) => (
                  <button
                    key={rev.id}
                    type="button"
                    onClick={() =>
                      setSelectedRevisionTab(
                        selectedRevisionTab === rev.id ? null : rev.id,
                      )
                    }
                    className={`rounded-lg px-3 py-1.5 text-xs font-mono font-medium transition-colors ${
                      selectedRevisionTab === rev.id
                        ? "bg-[#8E2638] text-white"
                        : "border border-[#77777D]/20 bg-[#171719] text-[#A6A1A0] hover:text-[#F5F2EE]"
                    }`}
                  >
                    Revisi #{rev.revision_number} (
                    {rev.assessment ? `${rev.assessment.final_score} pts` : "—"})
                  </button>
                ))}
              </div>

              {selectedRevisionTab !== null && (
                <div className="mt-3 rounded-xl border border-[#77777D]/20 bg-[#171719] p-4">
                  {(() => {
                    const rev = revisions.find(
                      (r) => r.id === selectedRevisionTab,
                    );
                    if (!rev) return null;
                    return (
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-mono text-[#77777D]">
                            REVISION #{rev.revision_number} ·{" "}
                            {formatDateTime(rev.created_at)}
                          </span>
                          {rev.assessment && (
                            <span
                              className={`rounded-full px-2 py-0.5 text-[11px] font-mono ${scoreBadgeClass(
                                rev.assessment.classification,
                              )}`}
                            >
                              Skor: {rev.assessment.final_score} / 100
                            </span>
                          )}
                        </div>
                        <h5 className="mt-2 text-sm font-semibold text-[#F5F2EE]">
                          {rev.title}
                        </h5>
                        <p className="mt-1 whitespace-pre-line text-xs leading-5 text-[#A6A1A0]">
                          {rev.description}
                        </p>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
