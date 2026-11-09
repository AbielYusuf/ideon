"use client";

import { useEffect, useMemo, useState } from "react";

import {
  createWebsiteActivity,
  fetchWebsites,
  fetchWebsiteUrls,
  updateWebsiteActivity,
  type Website,
  type WebsiteActivity,
  type WebsiteUrl,
} from "@/lib/api";
import {
  ACTIVITY_TYPES,
  FieldLabel,
  formatShortDate,
  inputClass,
  selectClass,
  todayIso,
} from "./ui";

export function ActivityForm({
  initial,
  defaultDate,
  defaultWebsiteId,
  lockWebsite = false,
  defaultUrlId,
  lockUrl = false,
  onSaved,
  onCancel,
}: {
  initial?: WebsiteActivity | null;
  defaultDate?: string;
  defaultWebsiteId?: number | null;
  lockWebsite?: boolean;
  defaultUrlId?: number | null;
  lockUrl?: boolean;
  onSaved: (activity: WebsiteActivity) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [activityType, setActivityType] = useState(
    initial?.activity_type ?? "Content Update",
  );
  const [status, setStatus] = useState<"planned" | "completed">(
    initial?.status ?? "planned",
  );
  const [plannedDate, setPlannedDate] = useState(
    initial?.planned_date ?? defaultDate ?? todayIso(),
  );
  const [completedDate, setCompletedDate] = useState(
    initial?.completed_date ?? todayIso(),
  );
  const [websiteId, setWebsiteId] = useState<number | null>(
    initial?.website_id ?? defaultWebsiteId ?? null,
  );
  const [websiteUrlId, setWebsiteUrlId] = useState<number | null>(
    initial?.website_url_id ?? defaultUrlId ?? null,
  );
  const [websites, setWebsites] = useState<Website[]>([]);
  const [urlSearch, setUrlSearch] = useState("");
  const [urls, setUrls] = useState<WebsiteUrl[]>([]);
  const [urlsError, setUrlsError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    fetchWebsites(controller.signal)
      .then((items) => {
        if (!active) return;
        setWebsites(items);
        setWebsiteId((current) => current ?? defaultWebsiteId ?? items[0]?.id ?? null);
      })
      .catch(() => {
        if (controller.signal.aborted || !active) return;
        // Website loading is secondary; URL loading reports the actionable error.
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [defaultWebsiteId]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    if (websiteId === null) {
      queueMicrotask(() => {
        if (!active) return;
        setUrls([]);
        setUrlsError(null);
      });
      return () => {
        active = false;
        controller.abort();
      };
    }

    queueMicrotask(() => {
      if (!active) return;
      setUrlsError(null);
      fetchWebsiteUrls(
        { websiteId, sort: "url", order: "asc" },
        controller.signal,
      )
        .then((items) => {
          if (!active) return;
          setUrls(items);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || !active) return;
          setUrlsError(
            err instanceof Error ? err.message : "Could not load website URLs.",
          );
        });
    });

    return () => {
      active = false;
      controller.abort();
    };
  }, [websiteId]);

  const selectedWebsite = useMemo(
    () => websites.find((item) => item.id === websiteId) ?? null,
    [websites, websiteId],
  );

  const selectedUrl = useMemo(
    () => urls.find((item) => item.id === websiteUrlId) ?? null,
    [urls, websiteUrlId],
  );

  const suggestions = useMemo(() => {
    const query = urlSearch.trim().toLowerCase();
    if (!query) return [];
    return urls
      .filter((item) => item.url.toLowerCase().includes(query))
      .slice(0, 8);
  }, [urls, urlSearch]);

  function changeWebsite(nextId: number | null) {
    setWebsiteId(nextId);
    setWebsiteUrlId(null);
    setUrlSearch("");
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);

    const payload = {
      title: title.trim(),
      description: description.trim(),
      activity_type: activityType,
      status,
      website_id: websiteId,
      website_url_id: websiteUrlId,
      planned_date: plannedDate,
      completed_date: status === "completed" ? completedDate || todayIso() : null,
    };

    try {
      const saved = initial
        ? await updateWebsiteActivity(initial.id, payload)
        : await createWebsiteActivity(payload);
      onSaved(saved);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save the activity.");
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <FieldLabel>Activity title</FieldLabel>
        <input
          className={inputClass}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="e.g. Update service page meta description"
          required
          maxLength={200}
          disabled={saving}
        />
      </div>

      <div>
        <FieldLabel>Description / notes</FieldLabel>
        <textarea
          className={`${inputClass} min-h-[96px] resize-y`}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="What changed, and why?"
          disabled={saving}
        />
      </div>

      <div>
        <FieldLabel>Website</FieldLabel>
        {lockWebsite ? (
          <div className="flex items-center gap-2 rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[#8E2638]" />
            <span className="text-sm text-[#F5F2EE]">
              {selectedWebsite?.name ?? "Selected website"}
            </span>
            {selectedWebsite ? (
              <span className="font-mono text-[10px] text-[#77777D]">
                {selectedWebsite.domain}
              </span>
            ) : null}
          </div>
        ) : (
          <select
            className={selectClass}
            value={websiteId ?? ""}
            onChange={(event) =>
              changeWebsite(
                event.target.value ? Number(event.target.value) : null,
              )
            }
            disabled={saving}
            required
          >
            {websites.length === 0 ? <option value="">Loading websites…</option> : null}
            {websites.map((website) => (
              <option key={website.id} value={website.id}>
                {website.name} · {website.domain}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <FieldLabel>Activity type</FieldLabel>
          <select
            className={selectClass}
            value={activityType}
            onChange={(event) => setActivityType(event.target.value)}
            disabled={saving}
          >
            {ACTIVITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div>
          <FieldLabel>Status</FieldLabel>
          <select
            className={selectClass}
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as "planned" | "completed")
            }
            disabled={saving}
          >
            <option value="planned">Planned</option>
            <option value="completed">Completed</option>
          </select>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <FieldLabel>Planned date</FieldLabel>
          <input
            type="date"
            className={inputClass}
            value={plannedDate}
            onChange={(event) => setPlannedDate(event.target.value)}
            required
            disabled={saving}
          />
        </div>
        {status === "completed" ? (
          <div>
            <FieldLabel>Actual completion date</FieldLabel>
            <input
              type="date"
              className={inputClass}
              value={completedDate}
              onChange={(event) => setCompletedDate(event.target.value)}
              disabled={saving}
            />
          </div>
        ) : (
          <div className="flex items-end pb-2">
            <p className="text-xs leading-5 text-[#77777D]">
              The planned date is preserved even after the activity is
              completed.
            </p>
          </div>
        )}
      </div>

      <div>
        <FieldLabel>
          Associated URL{" "}
          <span className="normal-case tracking-normal text-[#77777D]/70">
            (optional)
          </span>
        </FieldLabel>

        {selectedUrl ? (
          <div className="flex items-center justify-between gap-3 rounded border border-[#77777D]/30 bg-[#171719] px-3 py-2">
            <span className="truncate font-mono text-xs text-[#E8E3DC]">
              {selectedUrl.url}
            </span>
            {!lockUrl ? (
              <button
                type="button"
                onClick={() => setWebsiteUrlId(null)}
                className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-[#E58A9B] hover:text-white"
              >
                Clear
              </button>
            ) : null}
          </div>
        ) : websiteId === null ? (
          <p className="text-sm text-[#77777D]">
            Select a website before associating a URL.
          </p>
        ) : (
          <div className="relative">
            <input
              className={inputClass}
              value={urlSearch}
              onChange={(event) => setUrlSearch(event.target.value)}
              placeholder={`Search ${selectedWebsite?.name ?? "website"} URLs…`}
              disabled={saving}
            />
            {suggestions.length > 0 ? (
              <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded border border-[#77777D]/40 bg-[#1C1B1E] shadow-xl">
                {suggestions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setWebsiteUrlId(item.id);
                      setUrlSearch("");
                    }}
                    className="block w-full border-b border-[#222124] px-3 py-2 text-left font-mono text-xs text-[#A6A1A0] last:border-b-0 hover:bg-[#222124] hover:text-[#F5F2EE]"
                  >
                    {item.url}
                  </button>
                ))}
              </div>
            ) : null}
            {urlsError ? (
              <p className="mt-1 text-xs text-[#E58A9B]">{urlsError}</p>
            ) : (
              <p className="mt-1 text-xs text-[#77777D]">
                Only URLs belonging to the selected website are available. Leave
                empty for general website work.
              </p>
            )}
          </div>
        )}

        {!selectedUrl && websiteId !== null && urls.length > 0 ? (
          <p className="mt-1 text-[10px] text-[#77777D]">
            {urls.length} URL{urls.length === 1 ? "" : "s"} available for{" "}
            {selectedWebsite?.name ?? "this website"}.
          </p>
        ) : null}
        {selectedUrl ? (
          <p className="mt-1 text-[10px] text-[#77777D]">
            {selectedWebsite?.name ?? selectedUrl.website_name} · last activity:{" "}
            {formatShortDate(selectedUrl.last_activity_date)} ·{" "}
            {selectedUrl.activity_count} recorded
          </p>
        ) : null}
      </div>

      {error ? (
        <div className="rounded border border-[#8E2638]/40 bg-[#8E2638]/10 px-3 py-2 text-sm text-[#E58A9B]">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="submit"
          disabled={saving || websiteId === null}
          className="rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 font-mono text-xs uppercase tracking-wider text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "Saving…" : initial ? "Save changes" : "Create activity"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded border border-[#77777D]/30 bg-[#171719] px-4 py-2 font-mono text-xs uppercase tracking-wider text-[#A6A1A0] transition-colors hover:border-[#77777D]/60 disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
