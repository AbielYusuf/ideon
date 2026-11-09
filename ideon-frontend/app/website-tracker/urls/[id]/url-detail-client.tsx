"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { fetchWebsiteUrl, type WebsiteUrlDetail } from "@/lib/api";
import { ActivityForm } from "../../activity-form";
import {
  ErrorBlock,
  LoadingBlock,
  Modal,
  StatusBadge,
  formatLongDate,
  formatShortDate,
} from "../../ui";
import { readStoredWebsiteId, storeWebsiteId } from "../../website-context";

export function UrlDetailClient() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const urlId = Array.isArray(params.id) ? params.id[0] : params.id;
  const requestedWebsite = Number(searchParams.get("website"));
  const scopedWebsiteId =
    Number.isInteger(requestedWebsite) && requestedWebsite > 0
      ? requestedWebsite
      : (readStoredWebsiteId() ?? undefined);

  const [detail, setDetail] = useState<WebsiteUrlDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const reload = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!urlId) return;
    const controller = new AbortController();
    let active = true;

    queueMicrotask(() => {
      if (!active) return;
      setLoading(true);
      setError(null);
      fetchWebsiteUrl(urlId, scopedWebsiteId, controller.signal)
        .then((payload) => {
          if (!active) return;
          setDetail(payload);
          storeWebsiteId(payload.website_id);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || !active) return;
          setError(
            err instanceof Error ? err.message : "Could not load this URL.",
          );
          setLoading(false);
        });
    });

    return () => {
      active = false;
      controller.abort();
    };
  }, [urlId, scopedWebsiteId, revision]);

  return (
    <div className="space-y-5">
      <Link
        href="/website-tracker/urls"
        className="inline-block font-mono text-[10px] uppercase tracking-wider text-[#A6A1A0] hover:text-[#F5F2EE]"
      >
        ← Back to URL Library
      </Link>

      {notice ? (
        <div className="rounded border border-emerald-700/40 bg-emerald-900/20 px-4 py-2 text-sm text-emerald-200">
          {notice}
        </div>
      ) : null}

      {error ? <ErrorBlock message={error} /> : null}

      {loading ? (
        <LoadingBlock label="Loading URL history…" />
      ) : detail ? (
        <>
          <section className="rounded-lg border border-[#222124] bg-[#1C1B1E]/80 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-[#8E2638]">
                {detail.website_name}
              </p>
              <span className="rounded border border-[#77777D]/30 px-2 py-0.5 font-mono text-[9px] text-[#A6A1A0]">
                {detail.website_domain}
              </span>
            </div>
            <h2 className="mt-1 break-all font-mono text-sm text-[#F5F2EE] sm:text-base">
              {detail.url}
            </h2>
            <p className="mt-2 text-xs text-[#77777D]">
              Imported {formatShortDate(detail.created_at.slice(0, 10))}
              {detail.sitemap_last_modified
                ? ` · sitemap lastmod ${detail.sitemap_last_modified}`
                : ""}
            </p>

            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: "Activities", value: detail.activity_count },
                { label: "Planned", value: detail.planned_count },
                { label: "Completed", value: detail.completed_count },
                {
                  label: "Last activity",
                  value: formatShortDate(detail.last_activity_date),
                },
              ].map((metric) => (
                <div
                  key={metric.label}
                  className="rounded border border-[#222124] bg-[#171719] px-3 py-3"
                >
                  <p className="font-mono text-[9px] uppercase tracking-widest text-[#77777D]">
                    {metric.label}
                  </p>
                  <p className="mt-1 font-mono text-lg text-[#F5F2EE]">
                    {metric.value}
                  </p>
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={() => setFormOpen(true)}
              className="mt-5 rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 font-mono text-xs uppercase tracking-wider text-white hover:opacity-90"
            >
              + Add activity for this URL
            </button>
          </section>

          <section className="rounded-lg border border-[#222124] bg-[#1C1B1E]/80">
            <div className="border-b border-[#222124] px-5 py-3">
              <h3 className="font-mono text-xs uppercase tracking-widest text-[#E8E3DC]">
                Activity history
              </h3>
              <p className="mt-1 text-xs text-[#77777D]">
                Chronological record of planned and completed work.
              </p>
            </div>

            {detail.activities.length === 0 ? (
              <div className="px-5 py-10 text-center">
                <p className="font-mono text-xs uppercase tracking-widest text-[#A6A1A0]">
                  No activity recorded
                </p>
                <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#77777D]">
                  Use the button above to document the first change for this
                  URL.
                </p>
              </div>
            ) : (
              <ol className="relative space-y-0 px-5 py-4">
                {detail.activities.map((activity) => (
                  <li
                    key={activity.id}
                    className="relative border-l border-[#222124] pb-5 pl-5 last:pb-0"
                  >
                    <span
                      className={`absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full border ${
                        activity.status === "planned"
                          ? "border-[#A52A42] bg-[#8E2638]"
                          : "border-[#A6A1A0] bg-[#E8E3DC]"
                      }`}
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={activity.status} compact />
                      <span className="font-mono text-[9px] uppercase tracking-wider text-[#77777D]">
                        {activity.activity_type}
                      </span>
                      <span className="ml-auto font-mono text-[10px] text-[#A6A1A0]">
                        {formatLongDate(
                          activity.completed_date ?? activity.planned_date,
                        )}
                      </span>
                    </div>
                    <h4 className="mt-1.5 text-sm font-medium text-[#E8E3DC]">
                      {activity.title}
                    </h4>
                    {activity.description ? (
                      <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-[#A6A1A0]">
                        {activity.description}
                      </p>
                    ) : null}
                    <p className="mt-1.5 font-mono text-[10px] text-[#77777D]">
                      Planned {formatShortDate(activity.planned_date)}
                      {activity.completed_date
                        ? ` · Completed ${formatShortDate(activity.completed_date)}`
                        : ""}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      ) : null}

      {formOpen && detail ? (
        <Modal
          title="New activity"
          eyebrow={detail.url}
          onClose={() => setFormOpen(false)}
        >
          <ActivityForm
            defaultWebsiteId={detail.website_id}
            lockWebsite
            defaultUrlId={detail.id}
            lockUrl
            onCancel={() => setFormOpen(false)}
            onSaved={() => {
              setFormOpen(false);
              setNotice("Activity created.");
              reload();
            }}
          />
        </Modal>
      ) : null}
    </div>
  );
}
