"use client";

import { useEffect, useRef, useState } from "react";

import {
  fetchAssessments,
  formatDateTime,
  messageFromError,
  prepareAssessment,
  refineAssessment,
  scoreAssessment,
  type AssessmentAnalysis,
  type AssessmentResult,
  type ClarificationAnswer,
  type Idea,
  type RefinedIdea,
} from "@/lib/api";

type Phase =
  | "idle"
  | "preparing"
  | "analysis"
  | "refining"
  | "refined"
  | "scoring"
  | "result";

type HistoryState =
  | { phase: "loading" }
  | { phase: "loaded"; assessments: AssessmentResult[] }
  | { phase: "error"; message: string };

const busyPhases: Phase[] = ["preparing", "refining", "scoring"];

function formatWeight(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

function classificationStyle(classification: string): string {
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

function TextList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div>
      <h4 className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
        {title}
      </h4>
      <ul className="mt-2 space-y-1.5 text-xs leading-5 text-[#A6A1A0]">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className="flex gap-2">
            <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#8E2638]" />
            <span className="break-words">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NarrativeSections({
  analysis,
}: {
  analysis: AssessmentResult | AssessmentAnalysis;
}) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <TextList title="Key strengths // Strengths" items={analysis.key_strengths} />
      <TextList title="Key weaknesses // Weaknesses" items={analysis.key_weaknesses} />
      <TextList title="Missing information // Missing Info" items={analysis.missing_information} />
      <TextList
        title="Critical assumptions // Assumptions"
        items={analysis.critical_assumptions}
      />
      <TextList title="Uncertainty notes // Uncertainty" items={analysis.uncertainty_notes} />
    </div>
  );
}

function ResultBody({ result }: { result: AssessmentResult }) {
  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
          Summary // Executive Summary
        </h4>
        <p className="mt-2 text-xs leading-6 text-[#E8E3DC]">{result.summary}</p>
      </div>

      <div className="space-y-3">
        <h4 className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
          Criterion Breakdown // Evaluation Breakdown
        </h4>
        {result.criteria.map((criterion) => (
          <div
            key={criterion.criterion}
            className="rounded-xl border border-[#77777D]/20 bg-[#171719]/80 p-4"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h5 className="text-xs font-semibold text-[#F5F2EE] font-mono uppercase tracking-wider">
                {criterion.criterion}
              </h5>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="text-[#77777D]">{formatWeight(criterion.weight)} wt</span>
                <span className="font-semibold text-[#E8E3DC]">
                  {criterion.score}/100
                </span>
                <span className="rounded bg-[#8E2638]/20 border border-[#8E2638]/30 px-1.5 py-0.5 text-[11px] text-[#E8E3DC]">
                  {criterion.weighted_score} pts
                </span>
              </div>
            </div>
            <dl className="mt-3 space-y-2 text-xs leading-5 text-[#A6A1A0]">
              <div>
                <dt className="text-[10px] font-mono text-[#77777D] uppercase">Reasoning</dt>
                <dd className="mt-0.5 break-words text-[#E8E3DC]">{criterion.reasoning}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-mono text-[#77777D] uppercase">Evidence</dt>
                <dd className="mt-0.5 break-words">{criterion.evidence}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-mono text-[#77777D] uppercase">Assumptions</dt>
                <dd className="mt-0.5 break-words">{criterion.assumptions}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <NarrativeSections analysis={result} />
    </div>
  );
}

function ResultHeading({ result }: { result: AssessmentResult }) {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex items-baseline gap-2 font-mono">
        <span className="text-3xl font-bold tracking-tight text-[#F5F2EE]">
          {result.final_score}
        </span>
        <span className="text-xs text-[#77777D]">/ 100</span>
      </div>
      <span
        className={`rounded-full px-3 py-0.5 text-xs font-mono font-semibold ${classificationStyle(
          result.classification,
        )}`}
      >
        {result.classification}
      </span>
      <span className="text-xs font-mono text-[#77777D]">
        {formatDateTime(result.created_at)}
      </span>
    </div>
  );
}

function ResultCard({
  result,
  collapsible = false,
}: {
  result: AssessmentResult;
  collapsible?: boolean;
}) {
  const evaluated = (
    <div className="mt-3 rounded-xl border border-[#77777D]/15 bg-[#171719]/60 p-3.5">
      <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
        Evaluated Snapshot // Assessment Target
      </p>
      <p className="mt-1 text-xs font-semibold break-words text-[#E8E3DC]">
        {result.evaluated_title}
      </p>
      <p className="mt-1 whitespace-pre-line break-words text-[11px] leading-5 text-[#A6A1A0]">
        {result.evaluated_description}
      </p>
    </div>
  );

  if (!collapsible) {
    return (
      <div className="rounded-2xl border border-[#77777D]/20 bg-[#222124]/70 p-5 sm:p-6 shadow-xl">
        <ResultHeading result={result} />
        {evaluated}
        <div className="mt-5">
          <ResultBody result={result} />
        </div>
      </div>
    );
  }

  return (
    <details className="group rounded-xl border border-[#77777D]/20 bg-[#222124]/60">
      <summary className="cursor-pointer list-none p-4 marker:hidden focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#A52A42]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold text-[#F5F2EE]">
              {result.evaluated_title}
            </p>
            <p className="mt-0.5 text-[11px] font-mono text-[#77777D]">
              {formatDateTime(result.created_at)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3 font-mono">
            <span className="text-xs font-semibold text-[#E8E3DC]">
              {result.final_score} pts
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${classificationStyle(
                result.classification,
              )}`}
            >
              {result.classification}
            </span>
          </div>
        </div>
      </summary>
      <div className="border-t border-[#77777D]/15 p-4">
        {evaluated}
        <div className="mt-4">
          <ResultBody result={result} />
        </div>
      </div>
    </details>
  );
}

export default function AssessmentPanel({
  idea,
  onAssessmentCompleted,
}: {
  idea: Idea;
  onAssessmentCompleted?: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [analysis, setAnalysis] = useState<AssessmentAnalysis | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [refined, setRefined] = useState<RefinedIdea | null>(null);
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryState>({ phase: "loading" });
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchAssessments(idea.id, controller.signal)
      .then((assessments) => {
        if (!controller.signal.aborted) {
          setHistory({ phase: "loaded", assessments });
        }
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) {
          setHistory({
            phase: "error",
            message: messageFromError(requestError),
          });
        }
      });

    return () => controller.abort();
  }, [idea.id]);

  useEffect(() => {
    return () => requestRef.current?.abort();
  }, []);

  const beginRequest = () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    return controller;
  };

  const resetWorkflow = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    setPhase("idle");
    setAnalysis(null);
    setAnswers([]);
    setRefined(null);
    setResult(null);
    setError(null);
  };

  const startAssessment = async () => {
    const controller = beginRequest();

    setError(null);
    setAnalysis(null);
    setAnswers([]);
    setRefined(null);
    setResult(null);
    setPhase("preparing");

    try {
      const response = await prepareAssessment(idea.id, controller.signal);

      if (controller.signal.aborted) {
        return;
      }

      setAnalysis(response.analysis);
      setAnswers(response.analysis.clarifying_questions.map(() => ""));
      setPhase("analysis");
    } catch (requestError) {
      if (controller.signal.aborted) {
        return;
      }

      setError(messageFromError(requestError));
      setPhase("idle");
    }
  };

  const refineIdea = async () => {
    if (!analysis) {
      return;
    }

    const controller = beginRequest();
    const clarificationAnswers: ClarificationAnswer[] =
      analysis.clarifying_questions.map((question, index) => ({
        question,
        answer: answers[index] ?? "",
      }));

    setError(null);
    setPhase("refining");

    try {
      const response = await refineAssessment(
        idea.id,
        analysis,
        clarificationAnswers,
        controller.signal,
      );

      if (controller.signal.aborted) {
        return;
      }

      setRefined(response);
      setPhase("refined");
    } catch (requestError) {
      if (controller.signal.aborted) {
        return;
      }

      setError(messageFromError(requestError));
      setPhase("analysis");
    }
  };

  const approveAndScore = async () => {
    if (!analysis || !refined) {
      return;
    }

    const controller = beginRequest();

    setError(null);
    setPhase("scoring");

    try {
      const response = await scoreAssessment(
        idea.id,
        {
          confirmed: true,
          analysis,
          confirmed_title: refined.title,
          confirmed_description: refined.description,
        },
        controller.signal,
      );

      if (controller.signal.aborted) {
        return;
      }

      setResult(response);
      setPhase("result");
      if (onAssessmentCompleted) {
        onAssessmentCompleted();
      }

      try {
        const assessments = await fetchAssessments(idea.id);
        setHistory({ phase: "loaded", assessments });
      } catch (historyError) {
        setHistory({
          phase: "error",
          message: messageFromError(historyError),
        });
      }
    } catch (requestError) {
      if (controller.signal.aborted) {
        return;
      }

      setError(messageFromError(requestError));
      setPhase("refined");
    }
  };

  const isBusy = busyPhases.includes(phase);
  const historyItems =
    history.phase === "loaded"
      ? history.assessments.filter(
          (assessment) =>
            !(phase === "result" && result && assessment.id === result.id),
        )
      : [];

  return (
    <section
      aria-labelledby="assessment-heading"
      className="mt-6 rounded-2xl border border-[#77777D]/20 bg-[#222124]/80 p-6 shadow-xl backdrop-blur sm:p-8"
    >
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#77777D]/15 pb-5">
        <div className="ribbon-accent pl-4">
          <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#E58A9B] font-semibold">
            AI EVALUATION PROTOCOL // RUBRIC ASSESSMENT
          </p>
          <h2
            id="assessment-heading"
            className="mt-1 text-lg font-bold tracking-tight text-[#F5F2EE] font-mono"
          >
            GEMINI 5-CRITERIA ASSESSMENT
          </h2>
          <p className="mt-1 max-w-lg text-xs leading-5 text-[#A6A1A0]">
            Analisis ide secara objektif, tanggapi pertanyaan klarifikasi, dan kalkulasi skor berdasarkan 5 kriteria akademik.
          </p>
        </div>
        {phase === "idle" && (
          <button
            type="button"
            onClick={startAssessment}
            className="rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#A52A42]"
          >
            Assess Idea
          </button>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-rose-800/40 bg-rose-950/60 p-3 text-xs text-rose-300 font-mono"
        >
          {error}
        </p>
      )}

      {isBusy && (
        <div
          aria-busy="true"
          role="status"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#77777D]/20 bg-[#171719]/80 px-4 py-3 text-xs text-[#E8E3DC]"
        >
          <div className="flex items-center gap-2.5 font-mono">
            <span className="h-2 w-2 rounded-full bg-[#A52A42] animate-ping" />
            <span>
              {phase === "preparing" && "GEMINI IS ANALYSING PROPOSAL ARCHIVE…"}
              {phase === "refining" && "GEMINI IS REFINING IDEA STRUCTURE…"}
              {phase === "scoring" && "GEMINI IS EVALUATING RUBRIC CRITERIA…"}
            </span>
          </div>
          <button
            type="button"
            onClick={resetWorkflow}
            className="rounded-lg border border-[#77777D]/30 bg-[#222124] px-3 py-1 text-[11px] font-mono text-[#A6A1A0] hover:text-white"
          >
            CANCEL
          </button>
        </div>
      )}

      {phase === "analysis" && analysis && (
        <div className="mt-6 space-y-6">
          <div className="rounded-xl border border-[#77777D]/20 bg-[#171719]/80 p-5">
            <h3 className="text-xs font-semibold text-[#F5F2EE] font-mono uppercase tracking-wider">
              Preparation Analysis // Initial Findings
            </h3>
            <p className="mt-2 whitespace-pre-line text-xs leading-6 text-[#E8E3DC]">
              {analysis.summary}
            </p>
            <div className="mt-5 border-t border-[#77777D]/15 pt-4">
              <NarrativeSections analysis={analysis} />
            </div>
          </div>

          <div className="rounded-xl border border-[#8E2638]/40 bg-[#8E2638]/10 p-5">
            <h3 className="text-xs font-semibold text-[#E8E3DC] font-mono uppercase tracking-wider">
              Clarifying Questions // Inquiries
            </h3>
            {analysis.clarifying_questions.length === 0 ? (
              <p className="mt-2 text-xs leading-5 text-[#A6A1A0]">
                Gemini tidak memerlukan klarifikasi tambahan. Anda dapat langsung melanjutkan ke tahap perbaikan.
              </p>
            ) : (
              <div className="mt-4 space-y-4">
                {analysis.clarifying_questions.map((question, index) => (
                  <div key={question}>
                    <label
                      htmlFor={`clarification-${index}`}
                      className="text-xs font-medium text-[#E8E3DC]"
                    >
                      {question}
                    </label>
                    <textarea
                      id={`clarification-${index}`}
                      rows={3}
                      value={answers[index] ?? ""}
                      onChange={(event) =>
                        setAnswers((current) =>
                          current.map((answer, answerIndex) =>
                            answerIndex === index
                              ? event.target.value
                              : answer,
                          ),
                        )
                      }
                      placeholder="Klarifikasi opsional untuk memperjelas konteks..."
                      className="mt-1.5 w-full resize-y rounded-xl border border-[#77777D]/25 bg-[#171719] px-3.5 py-2 text-xs leading-5 text-[#F5F2EE] outline-none placeholder:text-[#77777D] focus:border-[#A52A42] focus:ring-1 focus:ring-[#A52A42]"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={resetWorkflow}
              className="rounded-xl border border-[#77777D]/25 bg-[#171719] px-4 py-2 text-xs font-mono font-medium text-[#E8E3DC] hover:bg-[#222124]"
            >
              BATALKAN ASESMEN
            </button>
            <button
              type="button"
              onClick={refineIdea}
              className="rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110"
            >
              REFINE IDEA
            </button>
          </div>
        </div>
      )}

      {phase === "refined" && refined && (
        <div className="mt-6 space-y-5">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-[#77777D]/20 bg-[#171719]/80 p-5">
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#77777D]">
                Original Idea // Baseline
              </p>
              <h3 className="mt-1.5 text-sm font-semibold text-[#F5F2EE]">
                {idea.title}
              </h3>
              <p className="mt-2 whitespace-pre-line break-words text-xs leading-5 text-[#A6A1A0]">
                {idea.description}
              </p>
            </div>
            <div className="rounded-xl border border-[#8E2638]/40 bg-[#8E2638]/10 p-5">
              <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#E58A9B] font-semibold">
                Refined Preview // Proposed Form
              </p>
              <h3 className="mt-1.5 text-sm font-semibold text-[#F5F2EE]">
                {refined.title}
              </h3>
              <p className="mt-2 whitespace-pre-line break-words text-xs leading-5 text-[#E8E3DC]">
                {refined.description}
              </p>
            </div>
          </div>

          <p className="rounded-xl border border-[#8E2638]/30 bg-[#8E2638]/15 px-3.5 py-2 text-xs font-mono text-[#E8E3DC]">
            Persetujuan akan menilai versi yang disempurnakan ini. Ide asli di arsip tidak akan diubah.
          </p>

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={resetWorkflow}
              className="rounded-xl border border-[#77777D]/25 bg-[#171719] px-4 py-2 text-xs font-mono font-medium text-[#E8E3DC] hover:bg-[#222124]"
            >
              BATALKAN
            </button>
            <button
              type="button"
              onClick={approveAndScore}
              className="rounded-xl bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-white shadow-lg shadow-[#8E2638]/20 hover:brightness-110"
            >
              APPROVE & EXECUTE SCORING
            </button>
          </div>
        </div>
      )}

      {phase === "result" && result && (
        <div className="mt-6 space-y-5">
          <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/40 px-4 py-2.5 text-xs font-mono text-emerald-200">
            ✓ ASSESSMENT RECORD COMPLETE AND ARCHIVED.
          </div>
          <ResultCard result={result} />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={resetWorkflow}
              className="rounded-xl border border-[#77777D]/25 bg-[#171719] px-4 py-2 text-xs font-mono font-medium text-[#E8E3DC] hover:bg-[#222124]"
            >
              NILAI ULANG IDE
            </button>
          </div>
        </div>
      )}

      <div className="mt-8 border-t border-[#77777D]/15 pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-xs font-semibold text-[#F5F2EE] font-mono uppercase tracking-wider">
            Assessment History // Recorded Dossiers
          </h3>
          <p className="text-[11px] font-mono text-[#77777D]">
            Setiap evaluasi terikat pada snapshot masing-masing.
          </p>
        </div>

        {history.phase === "loading" && (
          <p className="mt-3 text-xs font-mono text-[#77777D]">Memuat riwayat asesmen…</p>
        )}

        {history.phase === "error" && (
          <p className="mt-3 rounded-xl border border-rose-800/40 bg-rose-950/60 p-2.5 text-xs text-rose-300 font-mono">
            Gagal memuat riwayat: {history.message}
          </p>
        )}

        {history.phase === "loaded" && history.assessments.length === 0 && (
          <p className="mt-3 text-xs font-mono text-[#77777D]">
            Belum ada asesmen yang selesai untuk ide ini.
          </p>
        )}

        {history.phase === "loaded" &&
          history.assessments.length > 0 &&
          historyItems.length === 0 && (
            <p className="mt-3 text-xs font-mono text-[#77777D]">
              Tidak ada riwayat asesmen sebelumnya.
            </p>
          )}

        {history.phase === "loaded" && historyItems.length > 0 && (
          <div className="mt-4 space-y-3">
            {historyItems.map((assessment) => (
              <ResultCard
                key={assessment.id}
                result={assessment}
                collapsible
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
