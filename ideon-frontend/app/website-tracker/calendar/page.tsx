"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  completeWebsiteActivity,
  deleteWebsiteActivity,
  fetchWebsites,
  fetchWebsiteActivities,
  type Website,
  type WebsiteActivity,
} from "@/lib/api";
import { ActivityForm } from "../activity-form";
import {
  ACTIVITY_TYPES,
  EmptyBlock,
  ErrorBlock,
  FieldLabel,
  LoadingBlock,
  Modal,
  StatusBadge,
  formatLongDate,
  formatMonth,
  formatShortDate,
  toIsoDate,
  todayIso,
} from "../ui";

function monthBounds(month: Date): { start: string; end: string } {
  const start = new Date(month.getFullYear(), month.getMonth(), 1);
  const end = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  return { start: toIsoDate(start), end: toIsoDate(end) };
}

function activityDates(activity: WebsiteActivity): string[] {
  if (
    activity.completed_date &&
    activity.completed_date !== activity.planned_date
  ) {
    return [activity.planned_date, activity.completed_date];
  }
  return [activity.planned_date];
}

type ModalState =
  | { kind: "create"; date: string }
  | { kind: "edit"; activity: WebsiteActivity }
  | { kind: "view"; activity: WebsiteActivity };

export default function CalendarPage() {
  const [month, setMonth] = useState<Date | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [today, setToday] = useState<string | null>(null);
  const [activities, setActivities] = useState<WebsiteActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [websiteFilter, setWebsiteFilter] = useState<number | "">("");
  const [websites, setWebsites] = useState<Website[]>([]);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      const now = new Date();
      setMonth(new Date(now.getFullYear(), now.getMonth(), 1));
      setSelectedDate(toIsoDate(now));
      setToday(toIsoDate(now));
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    fetchWebsites(controller.signal)
      .then((items) => {
        if (!active) return;
        setWebsites(items);
      })
      .catch(() => {
        if (controller.signal.aborted || !active) return;
        // The calendar still works with the All Websites filter if this fails.
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  useEffect(() => {
    if (!month) return;
    const controller = new AbortController();
    let active = true;
    const { start, end } = monthBounds(month);

    queueMicrotask(() => {
      if (!active) return;
      setLoading(true);
      setError(null);

      fetchWebsiteActivities(
        {
          start,
          end,
          status: statusFilter || undefined,
          activityType: typeFilter || undefined,
          websiteId: websiteFilter === "" ? undefined : websiteFilter,
        },
        controller.signal,
      )
        .then((items) => {
          if (!active) return;
          setActivities(items);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || !active) return;
          setError(
            err instanceof Error ? err.message : "Could not load activities.",
          );
          setLoading(false);
        });
    });

    return () => {
      active = false;
      controller.abort();
    };
  }, [month, statusFilter, typeFilter, websiteFilter, revision]);

  const byDate = useMemo(() => {
    const map = new Map<string, WebsiteActivity[]>();
    for (const activity of activities) {
      for (const date of activityDates(activity)) {
        const list = map.get(date) ?? [];
        if (!list.some((item) => item.id === activity.id)) {
          list.push(activity);
        }
        map.set(date, list);
      }
    }
    return map;
  }, [activities]);

  const calendarCells = useMemo(() => {
    if (!month) return [];
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const daysInMonth = new Date(
      month.getFullYear(),
      month.getMonth() + 1,
      0,
    ).getDate();
    const leading = first.getDay();
    const cells: Array<string | null> = [];
    for (let index = 0; index < leading; index += 1) {
      cells.push(null);
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      cells.push(
        toIsoDate(new Date(month.getFullYear(), month.getMonth(), day)),
      );
    }
    while (cells.length % 7 !== 0) {
      cells.push(null);
    }
    return cells;
  }, [month]);

  const selectedActivities = byDate.get(selectedDate ?? "") ?? [];

  function shiftMonth(delta: number) {
    setMonth((current) =>
      current
        ? new Date(current.getFullYear(), current.getMonth() + delta, 1)
        : current,
    );
  }

  function goToToday() {
    const now = new Date();
    setMonth(new Date(now.getFullYear(), now.getMonth(), 1));
    setSelectedDate(todayIso());
  }

  function announce(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 4500);
  }

  async function handleDelete(activity: WebsiteActivity) {
    if (
      !window.confirm(
        `Delete “${activity.title}”? The associated URL and its history will be kept.`,
      )
    ) {
      return;
    }
    try {
      await deleteWebsiteActivity(activity.id);
      setModal(null);
      announce("Activity deleted.");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not delete activity.");
    }
  }

  async function handleComplete(activity: WebsiteActivity) {
    try {
      const updated = await completeWebsiteActivity(activity.id, todayIso());
      setModal({ kind: "view", activity: updated });
      announce("Activity marked as completed.");
      refresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not complete activity.",
      );
    }
  }

  if (!month || !selectedDate || !today) {
    return <LoadingBlock label="Preparing calendar…" />;
  }

  return (
    <div className="space-y-5">
      {notice ? (
        <div className="rounded border border-emerald-700/40 bg-emerald-900/20 px-4 py-2 text-sm text-emerald-200">
          {notice}
        </div>
      ) : null}

      {error ? <ErrorBlock message={error} /> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-lg border border-[#222124] bg-[#1C1B1E]/80">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#222124] px-4 py-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => shiftMonth(-1)}
                className="rounded border border-[#77777D]/30 px-2.5 py-1 font-mono text-xs text-[#A6A1A0] hover:border-[#77777D]/60 hover:text-white"
                aria-label="Previous month"
              >
                ←
              </button>
              <h2 className="min-w-[150px] text-center font-mono text-sm uppercase tracking-widest text-[#F5F2EE]">
                {formatMonth(month)}
              </h2>
              <button
                type="button"
                onClick={() => shiftMonth(1)}
                className="rounded border border-[#77777D]/30 px-2.5 py-1 font-mono text-xs text-[#A6A1A0] hover:border-[#77777D]/60 hover:text-white"
                aria-label="Next month"
              >
                →
              </button>
              <button
                type="button"
                onClick={goToToday}
                className="ml-1 rounded border border-[#8E2638]/40 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-[#E58A9B] hover:border-[#8E2638]/70"
              >
                Today
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={websiteFilter}
                onChange={(event) =>
                  setWebsiteFilter(
                    event.target.value ? Number(event.target.value) : "",
                  )
                }
                className="rounded border border-[#8E2638]/40 bg-[#171719] px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[#E58A9B] focus:outline-none"
                aria-label="Filter by website"
              >
                <option value="">All Websites</option>
                {websites.map((website) => (
                  <option key={website.id} value={website.id}>
                    {website.name}
                  </option>
                ))}
              </select>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="rounded border border-[#77777D]/30 bg-[#171719] px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0] focus:outline-none"
                aria-label="Filter by status"
              >
                <option value="">All statuses</option>
                <option value="planned">Planned</option>
                <option value="completed">Completed</option>
              </select>
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                className="rounded border border-[#77777D]/30 bg-[#171719] px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0] focus:outline-none"
                aria-label="Filter by activity type"
              >
                <option value="">All types</option>
                {ACTIVITY_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setModal({ kind: "create", date: selectedDate })}
                className="rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-white hover:opacity-90"
              >
                + Activity
              </button>
            </div>
          </div>

          <div className="grid grid-cols-7 border-b border-[#222124] bg-[#171719]/60">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
              <div
                key={day}
                className="px-2 py-2 text-center font-mono text-[9px] uppercase tracking-widest text-[#77777D]"
              >
                {day}
              </div>
            ))}
          </div>

          {loading ? (
            <div className="p-4">
              <LoadingBlock label="Loading calendar…" />
            </div>
          ) : (
            <div className="grid grid-cols-7">
              {calendarCells.map((date, index) => {
                if (!date) {
                  return (
                    <div
                      key={`empty-${index}`}
                      className="min-h-[86px] border-b border-r border-[#222124] bg-[#171719]/40"
                    />
                  );
                }

                const dateActivities = byDate.get(date) ?? [];
                const planned = dateActivities.filter(
                  (activity) => activity.status === "planned",
                ).length;
                const completed = dateActivities.filter(
                  (activity) => activity.status === "completed",
                ).length;
                const isSelected = date === selectedDate;
                const isToday = date === today;
                const day = Number(date.slice(-2));

                return (
                  <button
                    key={date}
                    type="button"
                    onClick={() => setSelectedDate(date)}
                    className={`group min-h-[86px] border-b border-r border-[#222124] p-2 text-left transition-colors ${
                      isSelected
                        ? "bg-[#8E2638]/15"
                        : "bg-[#1C1B1E] hover:bg-[#222124]/70"
                    }`}
                  >
                    <span
                      className={`inline-flex h-6 w-6 items-center justify-center rounded-full font-mono text-xs ${
                        isToday
                          ? "bg-[#8E2638] text-white"
                          : isSelected
                            ? "text-[#F5F2EE]"
                            : "text-[#A6A1A0]"
                      }`}
                    >
                      {day}
                    </span>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {planned > 0 ? (
                        <span className="rounded-sm bg-[#8E2638]/40 px-1.5 py-0.5 font-mono text-[9px] text-[#E58A9B]">
                          {planned}P
                        </span>
                      ) : null}
                      {completed > 0 ? (
                        <span className="rounded-sm bg-[#77777D]/25 px-1.5 py-0.5 font-mono text-[9px] text-[#E8E3DC]">
                          {completed}C
                        </span>
                      ) : null}
                    </div>
                    {dateActivities.length > 0 ? (
                      <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-[#77777D]">
                        {dateActivities[0].title}
                      </p>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-4 border-t border-[#222124] px-4 py-2 font-mono text-[9px] uppercase tracking-wider text-[#77777D]">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-sm bg-[#8E2638]/60" /> Planned
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-[#E8E3DC]/70" /> Completed
            </span>
            <span className="ml-auto normal-case tracking-normal text-[#77777D]">
              Completion dates also appear on the calendar.
            </span>
          </div>
        </section>

        <aside className="rounded-lg border border-[#222124] bg-[#1C1B1E]/80">
          <div className="border-b border-[#222124] px-4 py-3">
            <p className="font-mono text-[10px] uppercase tracking-widest text-[#8E2638]">
              Selected date
            </p>
            <h2 className="mt-1 text-sm font-medium text-[#F5F2EE]">
              {formatLongDate(selectedDate)}
            </h2>
          </div>

          <div className="max-h-[560px] space-y-3 overflow-y-auto p-4">
            {selectedActivities.length === 0 ? (
              <EmptyBlock
                title="No activities"
                detail="Nothing is scheduled or recorded for this date yet."
              />
            ) : (
              selectedActivities.map((activity) => {
                const isPlannedHere =
                  activity.planned_date === selectedDate;
                const isCompletedHere =
                  activity.completed_date === selectedDate &&
                  activity.completed_date !== activity.planned_date;
                return (
                  <article
                    key={activity.id}
                    className="rounded border border-[#222124] bg-[#171719] p-3"
                  >
                    <div className="mb-1 flex items-start justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setModal({ kind: "view", activity })}
                        className="text-left text-sm font-medium text-[#E8E3DC] hover:text-white"
                      >
                        {activity.title}
                      </button>
                      <StatusBadge status={activity.status} compact />
                    </div>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D]">
                      {activity.activity_type}
                      {activity.website_name ? ` · ${activity.website_name}` : ""}
                    </p>
                    {isPlannedHere ? (
                      <p className="mt-1 text-[11px] text-[#A6A1A0]">
                        Planned for {formatShortDate(activity.planned_date)}
                        {isCompletedHere
                          ? ` · completed ${formatShortDate(activity.completed_date)}`
                          : ""}
                      </p>
                    ) : (
                      <p className="mt-1 text-[11px] text-[#A6A1A0]">
                        Completed {formatShortDate(activity.completed_date)} ·
                        planned {formatShortDate(activity.planned_date)}
                      </p>
                    )}
                    {activity.website_url ? (
                      <p className="mt-1 truncate font-mono text-[10px] text-[#77777D]">
                        {activity.website_url}
                      </p>
                    ) : null}
                  </article>
                );
              })
            )}

            <button
              type="button"
              onClick={() => setModal({ kind: "create", date: selectedDate })}
              className="w-full rounded border border-dashed border-[#77777D]/30 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0] hover:border-[#8E2638]/60 hover:text-[#E58A9B]"
            >
              + Add activity on this date
            </button>
          </div>
        </aside>
      </div>

      {modal?.kind === "create" || modal?.kind === "edit" ? (
        <Modal
          title={modal.kind === "edit" ? "Edit activity" : "New activity"}
          eyebrow="Website Tracker · Calendar"
          onClose={() => setModal(null)}
        >
          <ActivityForm
            initial={modal.kind === "edit" ? modal.activity : null}
            defaultDate={modal.kind === "create" ? modal.date : undefined}
            defaultWebsiteId={
              websiteFilter === "" ? undefined : websiteFilter
            }
            lockWebsite={websiteFilter !== ""}
            onCancel={() => setModal(null)}
            onSaved={(saved) => {
              setModal(null);
              setSelectedDate(saved.planned_date);
              announce(modal.kind === "edit" ? "Activity updated." : "Activity created.");
              refresh();
            }}
          />
        </Modal>
      ) : null}

      {modal?.kind === "view" ? (
        <Modal
          title={modal.activity.title}
          eyebrow="Activity record"
          onClose={() => setModal(null)}
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={modal.activity.status} />
              <span className="rounded border border-[#77777D]/30 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0]">
                {modal.activity.activity_type}
              </span>
              {modal.activity.website_name ? (
                <span className="rounded border border-[#8E2638]/40 bg-[#8E2638]/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[#E58A9B]">
                  {modal.activity.website_name}
                </span>
              ) : null}
            </div>

            <p className="whitespace-pre-wrap text-sm leading-6 text-[#E8E3DC]">
              {modal.activity.description || "No description recorded."}
            </p>

            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="rounded border border-[#222124] bg-[#171719] p-3">
                <dt className="font-mono text-[9px] uppercase tracking-wider text-[#77777D]">
                  Planned date
                </dt>
                <dd className="mt-1 text-sm text-[#F5F2EE]">
                  {formatLongDate(modal.activity.planned_date)}
                </dd>
              </div>
              <div className="rounded border border-[#222124] bg-[#171719] p-3">
                <dt className="font-mono text-[9px] uppercase tracking-wider text-[#77777D]">
                  Actual completion
                </dt>
                <dd className="mt-1 text-sm text-[#F5F2EE]">
                  {formatLongDate(modal.activity.completed_date)}
                </dd>
              </div>
            </dl>

            <div>
              <FieldLabel>Associated URL</FieldLabel>
              {modal.activity.website_url &&
              modal.activity.website_url_id !== null ? (
                <Link
                  href={`/website-tracker/urls/${modal.activity.website_url_id}?website=${modal.activity.website_id}`}
                  className="break-all font-mono text-xs text-[#E58A9B] hover:text-white"
                >
                  {modal.activity.website_url}
                </Link>
              ) : (
                <p className="text-sm text-[#77777D]">
                  General website work (no URL associated).
                </p>
              )}
            </div>

            <div className="flex flex-wrap gap-2 border-t border-[#222124] pt-4">
              <button
                type="button"
                onClick={() =>
                  setModal({ kind: "edit", activity: modal.activity })
                }
                className="rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-white hover:opacity-90"
              >
                Edit
              </button>
              {modal.activity.status === "planned" ? (
                <button
                  type="button"
                  onClick={() => handleComplete(modal.activity)}
                  className="rounded border border-[#77777D]/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[#E8E3DC] hover:border-[#E8E3DC]/70"
                >
                  Mark complete
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => handleDelete(modal.activity)}
                className="ml-auto rounded border border-[#8E2638]/50 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-[#E58A9B] hover:bg-[#8E2638]/15"
              >
                Delete
              </button>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
