"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  fetchShortcuts,
  createShortcut,
  updateShortcut,
  deleteShortcut,
  fetchHelperHealth,
  fetchHelperApplications,
  launchApplication,
  fetchHelperProjects,
  startProject,
  stopProject,
  createHelperApplication,
  updateHelperApplication,
  deleteHelperApplication,
  createHelperProject,
  updateHelperProject,
  deleteHelperProject,
  type WebShortcut,
  type WebShortcutCreate,
  type HelperApplication,
  type HelperApplicationInput,
  type HelperProject,
  type HelperProjectInput,
} from "@/lib/api";
import { useAuth } from "../auth-provider";

// ─── Status Badge ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: "running" | "stopped" | "error" }) {
  const styles = {
    running:
      "bg-emerald-900/40 text-emerald-300 border border-emerald-700/40",
    stopped: "bg-[#222124] text-[#A6A1A0] border border-[#77777D]/30",
    error: "bg-red-900/40 text-red-300 border border-red-700/40",
  };
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded ${styles[status]}`}
    >
      {status}
    </span>
  );
}

// ─── Helper Offline Banner ────────────────────────────────────────────────────

function HelperOfflineBanner() {
  return (
    <div className="border border-[#8E2638]/40 bg-[#8E2638]/10 rounded px-4 py-3 mb-4">
      <p className="font-mono text-xs text-[#E58A9B] uppercase tracking-wider mb-1">
        LOCAL HELPER UNAVAILABLE
      </p>
      <p className="text-[#A6A1A0] text-sm">
        Desktop applications and local projects require the Ideon Helper to be
        running.
      </p>
      <p className="text-[#A6A1A0] text-sm mt-1">
        Start it with:{" "}
        <code className="font-mono text-[#F5F2EE] bg-[#171719] px-1.5 py-0.5 rounded text-xs">
          python ideon-helper/helper.py
        </code>
      </p>
    </div>
  );
}

// ─── Shortcut Form ────────────────────────────────────────────────────────────

function ShortcutForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: Partial<WebShortcutCreate>;
  onSave: (data: WebShortcutCreate) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [category, setCategory] = useState(initial?.category ?? "");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await onSave({ name: name.trim(), url: url.trim(), category: category.trim() || undefined });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          Name
        </label>
        <input
          className="w-full bg-[#171719] border border-[#77777D]/30 rounded px-3 py-2 text-sm text-[#F5F2EE] placeholder-[#77777D] focus:outline-none focus:border-[#8E2638]/60"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. ChatGPT"
          required
          disabled={saving}
        />
      </div>
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          URL
        </label>
        <input
          className="w-full bg-[#171719] border border-[#77777D]/30 rounded px-3 py-2 text-sm text-[#F5F2EE] placeholder-[#77777D] focus:outline-none focus:border-[#8E2638]/60"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://..."
          type="url"
          required
          disabled={saving}
        />
      </div>
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          Category{" "}
          <span className="normal-case text-[#77777D]/60">(optional)</span>
        </label>
        <input
          className="w-full bg-[#171719] border border-[#77777D]/30 rounded px-3 py-2 text-sm text-[#F5F2EE] placeholder-[#77777D] focus:outline-none focus:border-[#8E2638]/60"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="e.g. AI Tools"
          disabled={saving}
        />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-xs uppercase tracking-wider rounded hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="px-4 py-2 bg-[#171719] border border-[#77777D]/30 text-[#A6A1A0] font-mono text-xs uppercase tracking-wider rounded hover:border-[#77777D]/60 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ─── Application Form ─────────────────────────────────────────────────────────

function argsFromText(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function ApplicationForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: HelperApplication;
  onSave: (data: HelperApplicationInput) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [executable, setExecutable] = useState(initial?.executable ?? "");
  const [argsText, setArgsText] = useState((initial?.args ?? []).join("\n"));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await onSave({
      name: name.trim(),
      description: description.trim(),
      executable: executable.trim(),
      args: argsFromText(argsText),
    });
  }

  const inputClass =
    "w-full bg-[#171719] border border-[#77777D]/30 rounded px-3 py-2 text-sm text-[#F5F2EE] placeholder-[#77777D] focus:outline-none focus:border-[#8E2638]/60";

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
            Name
          </label>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Visual Studio Code"
            required
            disabled={saving}
          />
        </div>
        <div>
          <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
            Executable
          </label>
          <input
            className={inputClass}
            value={executable}
            onChange={(e) => setExecutable(e.target.value)}
            placeholder="e.g. code.cmd or C:\Path\app.exe"
            required
            disabled={saving}
          />
        </div>
      </div>
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          Description
        </label>
        <input
          className={inputClass}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional description"
          disabled={saving}
        />
      </div>
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          Arguments <span className="normal-case text-[#77777D]/60">(one per line)</span>
        </label>
        <textarea
          className={`${inputClass} font-mono text-xs min-h-20`}
          value={argsText}
          onChange={(e) => setArgsText(e.target.value)}
          placeholder={"--new-window\nC:\\SigmaProject"}
          disabled={saving}
        />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-xs uppercase tracking-wider rounded hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="px-4 py-2 bg-[#171719] border border-[#77777D]/30 text-[#A6A1A0] font-mono text-xs uppercase tracking-wider rounded hover:border-[#77777D]/60 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ─── Project Form ─────────────────────────────────────────────────────────────

function ProjectForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: HelperProject;
  onSave: (data: HelperProjectInput) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [workingDirectory, setWorkingDirectory] = useState(
    initial?.working_directory ?? "",
  );
  const [executable, setExecutable] = useState(initial?.executable ?? "");
  const [argsText, setArgsText] = useState((initial?.args ?? []).join("\n"));
  const [localUrl, setLocalUrl] = useState(initial?.local_url ?? "");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await onSave({
      name: name.trim(),
      description: description.trim(),
      working_directory: workingDirectory.trim(),
      executable: executable.trim(),
      args: argsFromText(argsText),
      local_url: localUrl.trim() || null,
    });
  }

  const inputClass =
    "w-full bg-[#171719] border border-[#77777D]/30 rounded px-3 py-2 text-sm text-[#F5F2EE] placeholder-[#77777D] focus:outline-none focus:border-[#8E2638]/60";

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
            Name
          </label>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My Web App"
            required
            disabled={saving}
          />
        </div>
        <div>
          <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
            Executable
          </label>
          <input
            className={inputClass}
            value={executable}
            onChange={(e) => setExecutable(e.target.value)}
            placeholder="e.g. npm.cmd"
            required
            disabled={saving}
          />
        </div>
      </div>
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          Working Directory
        </label>
        <input
          className={inputClass}
          value={workingDirectory}
          onChange={(e) => setWorkingDirectory(e.target.value)}
          placeholder={"C:\\path\\to\\project"}
          required
          disabled={saving}
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
            Description
          </label>
          <input
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            disabled={saving}
          />
        </div>
        <div>
          <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
            Local URL <span className="normal-case text-[#77777D]/60">(optional)</span>
          </label>
          <input
            className={inputClass}
            value={localUrl}
            onChange={(e) => setLocalUrl(e.target.value)}
            placeholder="http://localhost:3000"
            type="url"
            disabled={saving}
          />
        </div>
      </div>
      <div>
        <label className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] block mb-1">
          Arguments <span className="normal-case text-[#77777D]/60">(one per line)</span>
        </label>
        <textarea
          className={`${inputClass} font-mono text-xs min-h-20`}
          value={argsText}
          onChange={(e) => setArgsText(e.target.value)}
          placeholder={"run\ndev"}
          disabled={saving}
        />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-xs uppercase tracking-wider rounded hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="px-4 py-2 bg-[#171719] border border-[#77777D]/30 text-[#A6A1A0] font-mono text-xs uppercase tracking-wider rounded hover:border-[#77777D]/60 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ─── Delete Confirm ───────────────────────────────────────────────────────────

function DeleteConfirm({
  name,
  onConfirm,
  onCancel,
  deleting,
}: {
  name: string;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
  deleting: boolean;
}) {
  return (
    <div className="flex items-center gap-3 mt-2">
      <span className="text-xs text-[#E58A9B]">
        Remove &ldquo;{name}&rdquo;?
      </span>
      <button
        onClick={onConfirm}
        disabled={deleting}
        className="px-3 py-1 bg-[#8E2638]/80 text-white font-mono text-[10px] uppercase tracking-wider rounded hover:bg-[#8E2638] transition-colors disabled:opacity-50"
      >
        {deleting ? "Removing…" : "Confirm"}
      </button>
      <button
        onClick={onCancel}
        disabled={deleting}
        className="px-3 py-1 bg-[#171719] border border-[#77777D]/30 text-[#A6A1A0] font-mono text-[10px] uppercase tracking-wider rounded hover:border-[#77777D]/60 transition-colors disabled:opacity-50"
      >
        Cancel
      </button>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function QuickAccessPage() {
  const { user } = useAuth();
  // Desktop apps and local project paths are administrator-only.
  const isAdmin = user?.role === "admin";

  // Helper health
  const [helperOnline, setHelperOnline] = useState<boolean | null>(() =>
    isAdmin ? null : false,
  );

  // Web Shortcuts state
  const [shortcuts, setShortcuts] = useState<WebShortcut[]>([]);
  const [shortcutsLoading, setShortcutsLoading] = useState(true);
  const [shortcutsError, setShortcutsError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [savingShortcut, setSavingShortcut] = useState(false);

  // Applications state
  const [applications, setApplications] = useState<HelperApplication[]>([]);
  const [appsLoading, setAppsLoading] = useState(false);
  const [appsError, setAppsError] = useState<string | null>(null);
  const [launchingId, setLaunchingId] = useState<string | null>(null);
  const [launchMessages, setLaunchMessages] = useState<Record<string, string>>({});

  // Projects state
  const [projects, setProjects] = useState<HelperProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [projectActions, setProjectActions] = useState<Record<string, boolean>>({});
  const [projectMessages, setProjectMessages] = useState<Record<string, string>>({});

  // Application CRUD state
  const [showAppForm, setShowAppForm] = useState(false);
  const [editingAppId, setEditingAppId] = useState<string | null>(null);
  const [deletingAppId, setDeletingAppId] = useState<string | null>(null);
  const [savingApp, setSavingApp] = useState(false);
  const [appFormError, setAppFormError] = useState<string | null>(null);

  // Project CRUD state
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [savingProject, setSavingProject] = useState(false);
  const [projectFormError, setProjectFormError] = useState<string | null>(null);

  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // ── Helpers ──────────────────────────────────────────────────────────────

  const checkHelper = useCallback(async () => {
    const online = await fetchHelperHealth();
    setHelperOnline(online);
    return online;
  }, []);

  const loadShortcuts = useCallback(async () => {
    setShortcutsLoading(true);
    setShortcutsError(null);
    try {
      const data = await fetchShortcuts();
      setShortcuts(data);
    } catch {
      setShortcutsError("Failed to load shortcuts. Is the backend running?");
    } finally {
      setShortcutsLoading(false);
    }
  }, []);

  const loadApplications = useCallback(async () => {
    setAppsLoading(true);
    setAppsError(null);
    try {
      const data = await fetchHelperApplications();
      setApplications(data);
    } catch (error: unknown) {
      setApplications([]);
      setAppsError(
        error instanceof Error
          ? error.message
          : "Failed to load desktop applications.",
      );
    } finally {
      setAppsLoading(false);
    }
  }, []);

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsError(null);
    try {
      const data = await fetchHelperProjects();
      setProjects(data);
    } catch (error: unknown) {
      setProjects([]);
      setProjectsError(
        error instanceof Error ? error.message : "Failed to load local projects.",
      );
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  const pollProjectStatuses = useCallback(async () => {
    if (!helperOnline) return;
    try {
      const data = await fetchHelperProjects();
      setProjects(data);
    } catch {
      // silent
    }
  }, [helperOnline]);

  // ── Initialization ────────────────────────────────────────────────────────

  useEffect(() => {
    loadShortcuts();
    if (!isAdmin) {
      return;
    }
    checkHelper().then((online) => {
      if (online) {
        loadApplications();
        loadProjects();
      }
    });
  }, [isAdmin, loadShortcuts, checkHelper, loadApplications, loadProjects]);

  // ── Status polling ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!isAdmin) return;
    if (helperOnline === null) return;
    if (!helperOnline) return;

    pollRef.current = setInterval(pollProjectStatuses, 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [isAdmin, helperOnline, pollProjectStatuses]);

  // ── Shortcut actions ──────────────────────────────────────────────────────

  async function handleAddShortcut(data: WebShortcutCreate) {
    setSavingShortcut(true);
    try {
      const created = await createShortcut(data);
      setShortcuts((prev) => [created, ...prev]);
      setShowAddForm(false);
    } catch {
      alert("Failed to create shortcut.");
    } finally {
      setSavingShortcut(false);
    }
  }

  async function handleEditShortcut(id: number, data: WebShortcutCreate) {
    setSavingShortcut(true);
    try {
      const updated = await updateShortcut(id, data);
      setShortcuts((prev) => prev.map((s) => (s.id === id ? updated : s)));
      setEditingId(null);
    } catch {
      alert("Failed to update shortcut.");
    } finally {
      setSavingShortcut(false);
    }
  }

  async function handleDeleteShortcut(id: number) {
    setDeletingId(id);
    try {
      await deleteShortcut(id);
      setShortcuts((prev) => prev.filter((s) => s.id !== id));
    } catch {
      alert("Failed to delete shortcut.");
    } finally {
      setDeletingId(null);
    }
  }

  // ── Application actions ───────────────────────────────────────────────────

  async function handleLaunch(id: string) {
    setLaunchingId(id);
    setLaunchMessages((prev) => ({ ...prev, [id]: "" }));
    try {
      await launchApplication(id);
      setLaunchMessages((prev) => ({ ...prev, [id]: "Launched." }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Launch failed.";
      setLaunchMessages((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setLaunchingId(null);
    }
  }

  async function handleAddApplication(data: HelperApplicationInput) {
    setSavingApp(true);
    setAppFormError(null);
    try {
      await createHelperApplication(data);
      await loadApplications();
      setShowAppForm(false);
    } catch (e: unknown) {
      setAppFormError(e instanceof Error ? e.message : "Failed to add application.");
    } finally {
      setSavingApp(false);
    }
  }

  async function handleEditApplication(id: string, data: HelperApplicationInput) {
    setSavingApp(true);
    setAppFormError(null);
    try {
      await updateHelperApplication(id, data);
      await loadApplications();
      setEditingAppId(null);
    } catch (e: unknown) {
      setAppFormError(e instanceof Error ? e.message : "Failed to update application.");
    } finally {
      setSavingApp(false);
    }
  }

  async function handleDeleteApplication(id: string) {
    setSavingApp(true);
    setAppsError(null);
    try {
      await deleteHelperApplication(id);
      await loadApplications();
    } catch (e: unknown) {
      setAppsError(e instanceof Error ? e.message : "Failed to delete application.");
    } finally {
      setSavingApp(false);
      setDeletingAppId(null);
    }
  }

  // ── Project actions ───────────────────────────────────────────────────────

  async function handleStartProject(id: string) {
    setProjectActions((prev) => ({ ...prev, [id]: true }));
    setProjectMessages((prev) => ({ ...prev, [id]: "" }));
    try {
      const res = await startProject(id);
      if (!res.success) {
        setProjectMessages((prev) => ({
          ...prev,
          [id]: res.error ?? "Failed to start.",
        }));
      }
      await pollProjectStatuses();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Start failed.";
      setProjectMessages((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setProjectActions((prev) => ({ ...prev, [id]: false }));
    }
  }

  async function handleStopProject(id: string) {
    setProjectActions((prev) => ({ ...prev, [id]: true }));
    setProjectMessages((prev) => ({ ...prev, [id]: "" }));
    try {
      const res = await stopProject(id);
      if (!res.success) {
        setProjectMessages((prev) => ({
          ...prev,
          [id]: res.error ?? "Failed to stop.",
        }));
      }
      await pollProjectStatuses();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Stop failed.";
      setProjectMessages((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setProjectActions((prev) => ({ ...prev, [id]: false }));
    }
  }

  async function handleAddProject(data: HelperProjectInput) {
    setSavingProject(true);
    setProjectFormError(null);
    try {
      await createHelperProject(data);
      await loadProjects();
      setShowProjectForm(false);
    } catch (e: unknown) {
      setProjectFormError(e instanceof Error ? e.message : "Failed to add project.");
    } finally {
      setSavingProject(false);
    }
  }

  async function handleEditProject(id: string, data: HelperProjectInput) {
    setSavingProject(true);
    setProjectFormError(null);
    try {
      await updateHelperProject(id, data);
      await loadProjects();
      setEditingProjectId(null);
    } catch (e: unknown) {
      setProjectFormError(e instanceof Error ? e.message : "Failed to update project.");
    } finally {
      setSavingProject(false);
    }
  }

  async function handleDeleteProject(id: string) {
    setSavingProject(true);
    setProjectsError(null);
    try {
      await deleteHelperProject(id);
      await loadProjects();
    } catch (e: unknown) {
      setProjectsError(e instanceof Error ? e.message : "Failed to delete project.");
    } finally {
      setSavingProject(false);
      setDeletingProjectId(null);
    }
  }

  // ── Render helpers ────────────────────────────────────────────────────────

  const shortcutsByCategory = shortcuts.reduce<Record<string, WebShortcut[]>>(
    (acc, s) => {
      const cat = s.category || "General";
      (acc[cat] ??= []).push(s);
      return acc;
    },
    {}
  );

  // ── UI ────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#171719] academy-grid">
      {/* ── Ruler ── */}
      <div className="ruler-ticks w-full" aria-hidden />

      {/* ── Main ── */}
      <main className="mx-auto max-w-5xl px-5 py-10">
        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-3 mb-2">
            <span className="font-mono text-[10px] uppercase tracking-widest text-[#77777D]">
              TOOLS · WORKSPACE LAUNCHER
            </span>
            {/* Helper status dot */}
            {isAdmin && (
              <>
                <span
                  className={`inline-block w-2 h-2 rounded-full ${
                    helperOnline === null
                      ? "bg-[#77777D]"
                      : helperOnline
                      ? "bg-emerald-400"
                      : "bg-[#8E2638]"
                  }`}
                  title={
                    helperOnline === null
                      ? "Checking helper…"
                      : helperOnline
                      ? "Local helper connected"
                      : "Local helper offline"
                  }
                />
                <span className="font-mono text-[10px] text-[#77777D]">
                  {helperOnline === null
                    ? "CHECKING…"
                    : helperOnline
                    ? "HELPER ONLINE"
                    : "HELPER OFFLINE"}
                </span>
              </>
            )}
          </div>
          <h1 className="text-2xl font-semibold text-[#F5F2EE] tracking-tight">
            Quick Access
          </h1>
          <p className="text-sm text-[#A6A1A0] mt-1">
            Your personal workspace launcher — web shortcuts, desktop apps, and
            local projects.
          </p>
        </div>

        {/* ════════════════════════════════════════════════════════════════════ */}
        {/* SECTION A: Web Shortcuts */}
        {/* ════════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <div className="flex items-center justify-between mb-5">
            <div className="ribbon-accent pl-4">
              <h2 className="font-mono text-xs uppercase tracking-widest text-[#E58A9B]">
                WEB SHORTCUTS
              </h2>
              <p className="text-[#A6A1A0] text-sm mt-0.5">
                Bookmarks that open in a new browser tab.
              </p>
            </div>
            {!showAddForm && (
              <button
                onClick={() => {
                  setShowAddForm(true);
                  setEditingId(null);
                }}
                className="px-4 py-2 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-xs uppercase tracking-wider rounded hover:opacity-90 transition-opacity"
              >
                + Add Shortcut
              </button>
            )}
          </div>

          {/* Add form */}
          {showAddForm && (
            <div className="bg-[#222124]/80 border border-[#77777D]/20 rounded-lg p-5 mb-5">
              <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] mb-4">
                NEW SHORTCUT
              </p>
              <ShortcutForm
                onSave={handleAddShortcut}
                onCancel={() => setShowAddForm(false)}
                saving={savingShortcut}
              />
            </div>
          )}

          {/* Loading / Error / Empty */}
          {shortcutsLoading && (
            <p className="font-mono text-xs text-[#77777D] animate-pulse">
              Loading shortcuts…
            </p>
          )}
          {!shortcutsLoading && shortcutsError && (
            <p className="text-sm text-[#E58A9B]">{shortcutsError}</p>
          )}
          {!shortcutsLoading && !shortcutsError && shortcuts.length === 0 && (
            <p className="text-sm text-[#A6A1A0]">
              No shortcuts yet. Add your first one above.
            </p>
          )}

          {/* Grouped by category */}
          {!shortcutsLoading &&
            !shortcutsError &&
            Object.entries(shortcutsByCategory).map(([cat, items]) => (
              <div key={cat} className="mb-6">
                <p className="font-mono text-[10px] uppercase tracking-widest text-[#77777D] mb-3">
                  {cat}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {items.map((s) => (
                    <div
                      key={s.id}
                      className="bg-[#222124]/80 border border-[#77777D]/20 rounded-lg p-4 flex flex-col gap-2 hover:border-[#77777D]/40 transition-colors"
                    >
                      {editingId === s.id ? (
                        <ShortcutForm
                          initial={s}
                          onSave={(data) => handleEditShortcut(s.id, data)}
                          onCancel={() => setEditingId(null)}
                          saving={savingShortcut}
                        />
                      ) : (
                        <>
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-[#F5F2EE] text-sm font-medium truncate">
                                {s.name}
                              </p>
                              <p className="text-[#A6A1A0] text-xs truncate mt-0.5">
                                {s.url}
                              </p>
                            </div>
                            <div className="flex gap-1 shrink-0">
                              <button
                                onClick={() => {
                                  setEditingId(s.id);
                                  setShowAddForm(false);
                                }}
                                className="p-1.5 text-[#77777D] hover:text-[#F5F2EE] transition-colors rounded"
                                title="Edit"
                              >
                                <svg
                                  className="w-3.5 h-3.5"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                                  />
                                </svg>
                              </button>
                              <button
                                onClick={() =>
                                  setDeletingId(
                                    deletingId === s.id ? null : s.id
                                  )
                                }
                                className="p-1.5 text-[#77777D] hover:text-[#E58A9B] transition-colors rounded"
                                title="Delete"
                              >
                                <svg
                                  className="w-3.5 h-3.5"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                  />
                                </svg>
                              </button>
                            </div>
                          </div>

                          {/* Delete confirm */}
                          {deletingId === s.id && (
                            <DeleteConfirm
                              name={s.name}
                              onConfirm={() => handleDeleteShortcut(s.id)}
                              onCancel={() => setDeletingId(null)}
                              deleting={deletingId === s.id && shortcutsLoading}
                            />
                          )}

                          <a
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-auto inline-block px-3 py-1.5 bg-[#171719] border border-[#77777D]/30 text-[#A6A1A0] font-mono text-[10px] uppercase tracking-wider rounded hover:border-[#8E2638]/60 hover:text-[#F5F2EE] transition-colors text-center"
                          >
                            Open →
                          </a>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </section>

        {isAdmin && (
          <>
        {/* ════════════════════════════════════════════════════════════════════ */}
        {/* SECTION B: Desktop Applications */}
        {/* ════════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <div className="flex items-center justify-between gap-3 mb-5">
            <div className="ribbon-accent pl-4">
              <h2 className="font-mono text-xs uppercase tracking-widest text-[#E58A9B]">
                DESKTOP APPLICATIONS
              </h2>
              <p className="text-[#A6A1A0] text-sm mt-0.5">
                Launch pre-configured desktop apps via the local helper.
              </p>
            </div>
            {helperOnline && !showAppForm && (
              <button
                onClick={() => {
                  setShowAppForm(true);
                  setEditingAppId(null);
                  setAppFormError(null);
                }}
                className="px-4 py-2 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-xs uppercase tracking-wider rounded hover:opacity-90 transition-opacity"
              >
                + Add Application
              </button>
            )}
          </div>

          {!helperOnline && helperOnline !== null && <HelperOfflineBanner />}

          {helperOnline === null && (
            <p className="font-mono text-xs text-[#77777D] animate-pulse">
              Checking helper connection…
            </p>
          )}

          {helperOnline && showAppForm && (
            <div className="bg-[#222124]/80 border border-[#77777D]/20 rounded-lg p-5 mb-5">
              <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] mb-4">
                NEW APPLICATION
              </p>
              {appFormError && (
                <p role="alert" className="text-sm text-[#E58A9B] mb-3">
                  {appFormError}
                </p>
              )}
              <ApplicationForm
                onSave={handleAddApplication}
                onCancel={() => setShowAppForm(false)}
                saving={savingApp}
              />
            </div>
          )}

          {helperOnline && appsLoading && (
            <p className="font-mono text-xs text-[#77777D] animate-pulse">
              Loading applications…
            </p>
          )}

          {helperOnline && !appsLoading && appsError && (
            <p role="alert" className="text-sm text-[#E58A9B]">
              {appsError}
            </p>
          )}

          {helperOnline && !appsLoading && !appsError && applications.length === 0 && (
            <p className="text-sm text-[#A6A1A0]">
              No applications configured. Use the Add Application button above.
            </p>
          )}

          {helperOnline && !appsLoading && applications.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {applications.map((app) => (
                <div
                  key={app.id}
                  className="bg-[#222124]/80 border border-[#77777D]/20 rounded-lg p-4 flex flex-col gap-3 hover:border-[#77777D]/40 transition-colors"
                >
                  {editingAppId === app.id ? (
                    <>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D]">
                        EDIT APPLICATION
                      </p>
                      {appFormError && (
                        <p role="alert" className="text-sm text-[#E58A9B]">
                          {appFormError}
                        </p>
                      )}
                      <ApplicationForm
                        initial={app}
                        onSave={(data) => handleEditApplication(app.id, data)}
                        onCancel={() => {
                          setEditingAppId(null);
                          setAppFormError(null);
                        }}
                        saving={savingApp}
                      />
                    </>
                  ) : (
                    <>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-[#F5F2EE] text-sm font-medium">
                            {app.name}
                          </p>
                          <p className="text-[#A6A1A0] text-xs mt-0.5">
                            {app.description}
                          </p>
                          <p className="text-[10px] font-mono text-[#77777D] mt-1 truncate">
                            {app.executable}
                            {app.args.length > 0 ? ` ${app.args.join(" ")}` : ""}
                          </p>
                        </div>
                        <div className="flex gap-1 shrink-0">
                          <button
                            onClick={() => {
                              setEditingAppId(app.id);
                              setShowAppForm(false);
                              setAppFormError(null);
                            }}
                            className="px-2 py-1 text-[#77777D] hover:text-[#F5F2EE] font-mono text-[10px] uppercase tracking-wider transition-colors rounded"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() =>
                              setDeletingAppId(
                                deletingAppId === app.id ? null : app.id,
                              )
                            }
                            className="px-2 py-1 text-[#77777D] hover:text-[#E58A9B] font-mono text-[10px] uppercase tracking-wider transition-colors rounded"
                          >
                            Delete
                          </button>
                        </div>
                      </div>

                      {deletingAppId === app.id && (
                        <DeleteConfirm
                          name={app.name}
                          onConfirm={() => handleDeleteApplication(app.id)}
                          onCancel={() => setDeletingAppId(null)}
                          deleting={savingApp}
                        />
                      )}

                      <div>
                        <button
                          onClick={() => handleLaunch(app.id)}
                          disabled={launchingId === app.id}
                          className="px-3 py-1.5 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-[10px] uppercase tracking-wider rounded hover:opacity-90 transition-opacity disabled:opacity-50 w-full"
                        >
                          {launchingId === app.id ? "Launching…" : "Launch"}
                        </button>
                        {launchMessages[app.id] && (
                          <p className="font-mono text-[10px] text-[#A6A1A0] mt-2">
                            {launchMessages[app.id]}
                          </p>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ════════════════════════════════════════════════════════════════════ */}
        {/* SECTION C: Local Projects */}
        {/* ════════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <div className="flex items-center justify-between gap-3 mb-5">
            <div className="ribbon-accent pl-4">
              <h2 className="font-mono text-xs uppercase tracking-widest text-[#E58A9B]">
                LOCAL PROJECTS
              </h2>
              <p className="text-[#A6A1A0] text-sm mt-0.5">
                Start, stop, and monitor local development servers.
              </p>
            </div>
            {helperOnline && !showProjectForm && (
              <button
                onClick={() => {
                  setShowProjectForm(true);
                  setEditingProjectId(null);
                  setProjectFormError(null);
                }}
                className="px-4 py-2 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-xs uppercase tracking-wider rounded hover:opacity-90 transition-opacity"
              >
                + Add Project
              </button>
            )}
          </div>

          {!helperOnline && helperOnline !== null && <HelperOfflineBanner />}

          {helperOnline === null && (
            <p className="font-mono text-xs text-[#77777D] animate-pulse">
              Checking helper connection…
            </p>
          )}

          {helperOnline && showProjectForm && (
            <div className="bg-[#222124]/80 border border-[#77777D]/20 rounded-lg p-5 mb-5">
              <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D] mb-4">
                NEW PROJECT
              </p>
              {projectFormError && (
                <p role="alert" className="text-sm text-[#E58A9B] mb-3">
                  {projectFormError}
                </p>
              )}
              <ProjectForm
                onSave={handleAddProject}
                onCancel={() => setShowProjectForm(false)}
                saving={savingProject}
              />
            </div>
          )}

          {helperOnline && projectsLoading && (
            <p className="font-mono text-xs text-[#77777D] animate-pulse">
              Loading projects…
            </p>
          )}

          {helperOnline && !projectsLoading && projectsError && (
            <p role="alert" className="text-sm text-[#E58A9B]">
              {projectsError}
            </p>
          )}

          {helperOnline && !projectsLoading && !projectsError && projects.length === 0 && (
            <p className="text-sm text-[#A6A1A0]">
              No projects configured. Use the Add Project button above.
            </p>
          )}

          {helperOnline && !projectsLoading && projects.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {projects.map((p) => {
                const acting = projectActions[p.id] ?? false;
                return (
                  <div
                    key={p.id}
                    className="bg-[#222124]/80 border border-[#77777D]/20 rounded-lg p-4 flex flex-col gap-3 hover:border-[#77777D]/40 transition-colors"
                  >
                    {editingProjectId === p.id ? (
                      <>
                        <p className="font-mono text-[10px] uppercase tracking-wider text-[#77777D]">
                          EDIT PROJECT
                        </p>
                        {projectFormError && (
                          <p role="alert" className="text-sm text-[#E58A9B]">
                            {projectFormError}
                          </p>
                        )}
                        <ProjectForm
                          initial={p}
                          onSave={(data) => handleEditProject(p.id, data)}
                          onCancel={() => {
                            setEditingProjectId(null);
                            setProjectFormError(null);
                          }}
                          saving={savingProject}
                        />
                      </>
                    ) : (
                      <>
                        {/* Header row */}
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-[#F5F2EE] text-sm font-medium">
                              {p.name}
                            </p>
                            <p className="text-[#A6A1A0] text-xs mt-0.5">
                              {p.description}
                            </p>
                          </div>
                          <div className="flex flex-col items-end gap-2 shrink-0">
                            <StatusBadge status={p.status} />
                            <div className="flex gap-1">
                              <button
                                onClick={() => {
                                  setEditingProjectId(p.id);
                                  setShowProjectForm(false);
                                  setProjectFormError(null);
                                }}
                                disabled={p.status === "running"}
                                title={
                                  p.status === "running"
                                    ? "Stop the project before editing."
                                    : "Edit project"
                                }
                                className="px-2 py-1 text-[#77777D] hover:text-[#F5F2EE] font-mono text-[10px] uppercase tracking-wider transition-colors rounded disabled:opacity-40 disabled:hover:text-[#77777D]"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() =>
                                  setDeletingProjectId(
                                    deletingProjectId === p.id ? null : p.id,
                                  )
                                }
                                className="px-2 py-1 text-[#77777D] hover:text-[#E58A9B] font-mono text-[10px] uppercase tracking-wider transition-colors rounded"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        </div>

                        {deletingProjectId === p.id && (
                          <DeleteConfirm
                            name={p.name}
                            onConfirm={() => handleDeleteProject(p.id)}
                            onCancel={() => setDeletingProjectId(null)}
                            deleting={savingProject}
                          />
                        )}

                        {/* Meta */}
                        <div className="space-y-1">
                          <div className="flex gap-2 text-[10px] font-mono">
                            <span className="text-[#77777D] uppercase tracking-wider shrink-0">
                              Dir:
                            </span>
                            <span className="text-[#A6A1A0] truncate">
                              {p.working_directory}
                            </span>
                          </div>
                          <div className="flex gap-2 text-[10px] font-mono">
                            <span className="text-[#77777D] uppercase tracking-wider shrink-0">
                              Cmd:
                            </span>
                            <span className="text-[#A6A1A0] truncate">
                              {p.development_command}
                            </span>
                          </div>
                          {p.pid && (
                            <div className="flex gap-2 text-[10px] font-mono">
                              <span className="text-[#77777D] uppercase tracking-wider shrink-0">
                                PID:
                              </span>
                              <span className="text-[#A6A1A0]">{p.pid}</span>
                            </div>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex gap-2 items-center">
                          {p.status !== "running" ? (
                            <button
                              onClick={() => handleStartProject(p.id)}
                              disabled={acting}
                              className="px-3 py-1.5 bg-gradient-to-r from-[#8E2638] to-[#A52A42] text-white font-mono text-[10px] uppercase tracking-wider rounded hover:opacity-90 transition-opacity disabled:opacity-50"
                            >
                              {acting ? "Starting…" : "Start"}
                            </button>
                          ) : (
                            <button
                              onClick={() => handleStopProject(p.id)}
                              disabled={acting}
                              className="px-3 py-1.5 bg-[#171719] border border-[#8E2638]/60 text-[#E58A9B] font-mono text-[10px] uppercase tracking-wider rounded hover:border-[#8E2638] transition-colors disabled:opacity-50"
                            >
                              {acting ? "Stopping…" : "Stop"}
                            </button>
                          )}

                          {p.status === "running" && p.local_url && (
                            <a
                              href={p.local_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 bg-[#171719] border border-[#77777D]/30 text-[#A6A1A0] font-mono text-[10px] uppercase tracking-wider rounded hover:border-[#77777D]/60 hover:text-[#F5F2EE] transition-colors"
                            >
                              Open →
                            </a>
                          )}
                        </div>

                        {projectMessages[p.id] && (
                          <p className="font-mono text-[10px] text-[#E58A9B]">
                            {projectMessages[p.id]}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
          </>
        )}

        {/* Footer */}
        <div className="border-t border-[#222124] pt-6 mt-6">
          <p className="font-mono text-[10px] text-[#77777D] uppercase tracking-widest">
            IDEON · QUICK ACCESS · WORKSPACE LAUNCHER
          </p>
        </div>
      </main>
    </div>
  );
}
