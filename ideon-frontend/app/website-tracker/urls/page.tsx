"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  fetchWebsites,
  fetchSitemapFiles,
  fetchWebsiteUrls,
  importSitemaps,
  type SitemapFile,
  type SitemapImportSummary,
  type Website,
  type WebsiteUrl,
} from "@/lib/api";
import {
  EmptyBlock,
  ErrorBlock,
  LoadingBlock,
  Modal,
  formatShortDate,
  inputClass,
  selectClass,
} from "../ui";
import { readStoredWebsiteId, storeWebsiteId } from "../website-context";

const SORT_OPTIONS = [
  { value: "url:asc", label: "URL A–Z" },
  { value: "url:desc", label: "URL Z–A" },
  { value: "activity_count:desc", label: "Most activities" },
  { value: "last_activity:desc", label: "Latest activity" },
  { value: "created_at:desc", label: "Recently imported" },
];

export default function UrlLibraryPage() {
  const [websites, setWebsites] = useState<Website[]>([]);
  const [websiteId, setWebsiteId] = useState<number | null>(null);
  const [websitesError, setWebsitesError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sortValue, setSortValue] = useState("url:asc");
  const [urls, setUrls] = useState<WebsiteUrl[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const [importOpen, setImportOpen] = useState(false);
  const [files, setFiles] = useState<SitemapFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SitemapImportSummary | null>(null);

  const [sort, order] = sortValue.split(":");
  const selectedWebsite =
    websites.find((item) => item.id === websiteId) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    fetchWebsites(controller.signal)
      .then((items) => {
        if (!active) return;
        setWebsites(items);
        setWebsiteId((current) => {
          if (current !== null) return current;
          const stored = readStoredWebsiteId();
          const preferred = items.find((item) => item.id === stored);
          return preferred?.id ?? items[0]?.id ?? null;
        });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || !active) return;
        setWebsitesError(
          err instanceof Error ? err.message : "Could not load websites.",
        );
        setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  useEffect(() => {
    if (websiteId === null) return;
    storeWebsiteId(websiteId);
  }, [websiteId]);

  useEffect(() => {
    if (websiteId === null) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      fetchWebsiteUrls(
        {
          websiteId,
          search: search.trim() || undefined,
          status: status || undefined,
          sort,
          order,
        },
        controller.signal,
      )
        .then((items) => {
          setUrls(items);
          setLoading(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          setError(err instanceof Error ? err.message : "Could not load URLs.");
          setLoading(false);
        });
    }, 220);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [websiteId, search, status, sort, order, revision]);

  function chooseWebsite(nextId: number) {
    setWebsiteId(nextId);
    setSummary(null);
    setImportError(null);
  }

  useEffect(() => {
    if (!importOpen) return;
    const controller = new AbortController();
    let active = true;

    queueMicrotask(() => {
      if (!active) return;
      setFilesLoading(true);
      setImportError(null);
      setSummary(null);
      fetchSitemapFiles(controller.signal)
        .then((items) => {
          if (!active) return;
          setFiles(items);
          setSelectedFiles(items.map((item) => item.filename));
          setFilesLoading(false);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || !active) return;
          setImportError(
            err instanceof Error ? err.message : "Could not list sitemap files.",
          );
          setFilesLoading(false);
        });
    });

    return () => {
      active = false;
      controller.abort();
    };
  }, [importOpen]);

  async function handleImport() {
    if (selectedFiles.length === 0 || websiteId === null) return;
    setImporting(true);
    setImportError(null);
    try {
      const result = await importSitemaps(websiteId, selectedFiles);
      setSummary(result);
      setRevision((value) => value + 1);
    } catch (err: unknown) {
      setImportError(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setImporting(false);
    }
  }

  function toggleFile(filename: string) {
    setSelectedFiles((current) =>
      current.includes(filename)
        ? current.filter((item) => item !== filename)
        : [...current, filename],
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-[#222124] bg-[#1C1B1E]/80 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-[#8E2638]">
              Website collection
            </p>
            <h2 className="mt-1 font-mono text-sm uppercase tracking-widest text-[#F5F2EE]">
              URL Library
            </h2>
            <p className="mt-1 text-sm text-[#A6A1A0]">
              {urls.length} URL{urls.length === 1 ? "" : "s"} in{" "}
              {selectedWebsite?.name ?? "the selected website"}.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            disabled={websiteId === null}
            className="w-fit rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 font-mono text-xs uppercase tracking-wider text-white hover:opacity-90 disabled:opacity-50"
          >
            Import sitemap
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Website selector">
          {websites.map((website) => {
            const active = website.id === websiteId;
            return (
              <button
                key={website.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => chooseWebsite(website.id)}
                className={`rounded border px-3 py-2 text-left transition-colors ${
                  active
                    ? "border-[#8E2638]/70 bg-[#8E2638]/20"
                    : "border-[#77777D]/25 bg-[#171719] hover:border-[#77777D]/50"
                }`}
              >
                <span
                  className={`block font-mono text-[11px] uppercase tracking-wider ${
                    active ? "text-[#E58A9B]" : "text-[#A6A1A0]"
                  }`}
                >
                  {website.name}
                </span>
                <span className="mt-0.5 block font-mono text-[9px] text-[#77777D]">
                  {website.domain} · {website.url_count} URLs
                </span>
              </button>
            );
          })}
          {websites.length === 0 && !websitesError ? (
            <span className="font-mono text-[10px] uppercase tracking-wider text-[#77777D]">
              Loading websites…
            </span>
          ) : null}
        </div>
        {websitesError ? (
          <p className="mt-2 text-xs text-[#E58A9B]">{websitesError}</p>
        ) : null}
      </div>

      <div className="grid gap-3 rounded-lg border border-[#222124] bg-[#1C1B1E]/80 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="lg:col-span-2">
          <label
            htmlFor="url-search"
            className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-[#77777D]"
          >
            Search
          </label>
          <input
            id="url-search"
            className={inputClass}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search imported URLs…"
          />
        </div>
        <div>
          <label
            htmlFor="status-filter"
            className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-[#77777D]"
          >
            Activity status
          </label>
          <select
            id="status-filter"
            className={selectClass}
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All URLs</option>
            <option value="planned">Has planned activity</option>
            <option value="completed">Has completed activity</option>
          </select>
        </div>
        <div>
          <label
            htmlFor="sort-filter"
            className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-[#77777D]"
          >
            Sort
          </label>
          <select
            id="sort-filter"
            className={selectClass}
            value={sortValue}
            onChange={(event) => setSortValue(event.target.value)}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error ? <ErrorBlock message={error} /> : null}

      {loading ? (
        <LoadingBlock label="Loading URL library…" />
      ) : urls.length === 0 ? (
        <EmptyBlock
          title={search || status ? "No matching URLs" : "URL library is empty"}
          detail={
            search || status
              ? "Try a broader search or remove the activity filter."
              : `No URLs are stored for ${selectedWebsite?.name ?? "this website"} yet. Place its sitemap XML in the project root, then use Import sitemap.`
          }
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#222124] bg-[#1C1B1E]/80">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead>
                <tr className="border-b border-[#222124] bg-[#171719]/70">
                  {[
                    "URL",
                    "Activities",
                    "Planned",
                    "Completed",
                    "Last activity",
                    "",
                  ].map((heading) => (
                    <th
                      key={heading || "actions"}
                      className="px-4 py-3 font-mono text-[9px] uppercase tracking-widest text-[#77777D]"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {urls.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-[#222124] last:border-b-0 hover:bg-[#222124]/40"
                  >
                    <td className="max-w-[420px] px-4 py-3">
                      <span className="block truncate font-mono text-xs text-[#E8E3DC]">
                        {item.url}
                      </span>
                      {item.sitemap_last_modified ? (
                        <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-wider text-[#77777D]">
                          sitemap lastmod {item.sitemap_last_modified}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#F5F2EE]">
                      {item.activity_count}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#E58A9B]">
                      {item.planned_count}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#A6A1A0]">
                      {item.completed_count}
                    </td>
                    <td className="px-4 py-3 text-xs text-[#A6A1A0]">
                      {formatShortDate(item.last_activity_date)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/website-tracker/urls/${item.id}?website=${item.website_id}`}
                        className="font-mono text-[10px] uppercase tracking-wider text-[#E58A9B] hover:text-white"
                      >
                        Open →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {importOpen ? (
        <Modal
          title="Import sitemap"
          eyebrow="Explicit local import"
          onClose={() => setImportOpen(false)}
        >
          <div className="space-y-4">
            <p className="text-sm leading-6 text-[#A6A1A0]">
              Importing into <span className="text-[#E8E3DC]">{selectedWebsite?.name ?? "the selected website"}</span>{" "}
              ({selectedWebsite?.domain ?? "website domain"}). Select an XML
              sitemap placed in the Ideon project root. Only URLs belonging to
              this domain are imported. Existing URLs and their activity history
              are preserved, and the file is not modified or required at runtime.
            </p>

            {filesLoading ? (
              <LoadingBlock label="Looking for sitemap files…" />
            ) : files.length === 0 ? (
              <div className="rounded border border-dashed border-[#77777D]/30 px-4 py-6 text-sm text-[#A6A1A0]">
                No `.xml` files were found in the project root. Place the sitemap
                there, then reopen this dialog.
              </div>
            ) : (
              <div className="space-y-2">
                <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D]">
                  Available files
                </p>
                {files.map((file) => (
                  <label
                    key={file.filename}
                    className="flex cursor-pointer items-center gap-3 rounded border border-[#222124] bg-[#171719] px-3 py-2 text-sm text-[#E8E3DC]"
                  >
                    <input
                      type="checkbox"
                      checked={selectedFiles.includes(file.filename)}
                      onChange={() => toggleFile(file.filename)}
                      className="accent-[#8E2638]"
                    />
                    <span className="font-mono text-xs">{file.filename}</span>
                  </label>
                ))}
              </div>
            )}

            {importError ? (
              <div className="rounded border border-[#8E2638]/40 bg-[#8E2638]/10 px-3 py-2 text-sm text-[#E58A9B]">
                {importError}
              </div>
            ) : null}

            {summary ? (
              <div className="rounded border border-emerald-700/40 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-100">
                <p className="font-mono text-[10px] uppercase tracking-wider text-emerald-300">
                  Import complete · {summary.website_name}
                </p>
                <p className="mt-1 font-mono text-[10px] text-emerald-200/80">
                  {summary.filenames.join(", ")}
                </p>
                <ul className="mt-2 grid gap-1 sm:grid-cols-2">
                  <li>URLs found: {summary.found}</li>
                  <li>Imported: {summary.imported}</li>
                  <li>Updated existing: {summary.updated}</li>
                  <li>Duplicates skipped: {summary.duplicates}</li>
                  <li>Invalid entries: {summary.invalid}</li>
                  <li>Unrelated domains: {summary.unrelated_domains}</li>
                  <li>Files processed: {summary.files_processed}</li>
                  {summary.sitemap_index ? (
                    <li>
                      Child sitemaps skipped: {summary.child_sitemaps_skipped}
                    </li>
                  ) : null}
                </ul>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2 border-t border-[#222124] pt-4">
              <button
                type="button"
                onClick={handleImport}
                disabled={
                  importing || selectedFiles.length === 0 || websiteId === null
                }
                className="rounded bg-gradient-to-r from-[#8E2638] to-[#A52A42] px-4 py-2 font-mono text-xs uppercase tracking-wider text-white hover:opacity-90 disabled:opacity-50"
              >
                {importing ? "Importing…" : "Import selected"}
              </button>
              <button
                type="button"
                onClick={() => setImportOpen(false)}
                className="rounded border border-[#77777D]/30 px-4 py-2 font-mono text-xs uppercase tracking-wider text-[#A6A1A0] hover:border-[#77777D]/60"
              >
                Close
              </button>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
