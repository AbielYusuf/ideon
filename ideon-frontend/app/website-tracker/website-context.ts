"use client";

const STORAGE_KEY = "ideon.website-tracker.websiteId";

export function readStoredWebsiteId(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

export function storeWebsiteId(websiteId: number): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, String(websiteId));
  } catch {
    // A blocked storage API must not break the tracker.
  }
}
