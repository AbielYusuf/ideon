export type Idea = {
  id: number;
  title: string;
  description: string;
  created_at: string;
  updated_at: string;
};

export type IdeaInput = {
  title: string;
  description: string;
};

export type AssessmentNarrative = {
  summary: string;
  key_strengths: string[];
  key_weaknesses: string[];
  missing_information: string[];
  critical_assumptions: string[];
  uncertainty_notes: string[];
};

export type AssessmentAnalysis = AssessmentNarrative & {
  clarifying_questions: string[];
  proposed_refined_title: string;
  proposed_refined_description: string;
};

export type AssessmentIdeaSnapshot = {
  id: number;
  title: string;
  description: string;
};

export type PrepareAssessmentResponse = {
  idea: AssessmentIdeaSnapshot;
  analysis: AssessmentAnalysis;
};

export type RefinedIdea = {
  title: string;
  description: string;
};

export type ClarificationAnswer = {
  question: string;
  answer: string;
};

export type CriterionAssessment = {
  criterion: string;
  score: number;
  weight: number;
  weighted_score: number;
  reasoning: string;
  evidence: string;
  assumptions: string;
};

export type AssessmentResult = AssessmentNarrative & {
  id: number;
  idea_id: number;
  evaluated_title: string;
  evaluated_description: string;
  criteria: CriterionAssessment[];
  final_score: number;
  classification: string;
  created_at: string;
};

export type ScoreAssessmentInput = {
  confirmed: boolean;
  analysis: AssessmentNarrative;
  confirmed_title: string;
  confirmed_description: string;
};

export type ImprovementSession = {
  id: number;
  idea_id: number;
  base_assessment_id: number;
  current_revision_id: number | null;
  status: "active" | "completed" | "cancelled";
  accepted_revision_count: number;
  created_at: string;
  updated_at: string;
};

export type ImprovementProposal = {
  id: number;
  session_id: number;
  proposal_attempt: number;
  input_revision_id: number | null;
  input_assessment_id: number;
  proposed_title: string;
  proposed_description: string;
  rationale: string;
  key_changes: string[];
  status: "pending" | "accepted" | "rejected" | "superseded";
  created_at: string;
};

export type IdeaRevision = {
  id: number;
  session_id: number;
  proposal_id: number;
  revision_number: number;
  title: string;
  description: string;
  assessment_id: number;
  created_at: string;
  assessment?: AssessmentResult | null;
};

export type ScoreDelta = {
  criterion: string;
  old_score: number;
  new_score: number;
  delta: number;
};

export type ScoreComparison = {
  old_final_score: number;
  new_final_score: number;
  final_score_delta: number;
  old_classification: string;
  new_classification: string;
  criteria_deltas: ScoreDelta[];
};

export type ProposalActionResponse = {
  action: "accept" | "reject" | "regenerate";
  session: ImprovementSession;
  proposal: ImprovementProposal;
  revision?: IdeaRevision | null;
  comparison?: ScoreComparison | null;
  next_proposal?: ImprovementProposal | null;
};

export type ImprovementSessionDetail = {
  session: ImprovementSession;
  current_text: {
    title: string;
    description: string;
  };
  current_assessment: AssessmentResult;
  revisions: IdeaRevision[];
  pending_proposal: ImprovementProposal | null;
  proposal_history: ImprovementProposal[];
};

export const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
export const configurationError = apiUrl
  ? null
  : "NEXT_PUBLIC_API_URL is not configured. Add it to your .env.local file.";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const CSRF_COOKIE = "ideon_csrf";

export const AUTH_EXPIRED_EVENT = "ideon:auth-expired";

const AUTH_PATHS = [
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/logout",
  "/api/auth/me",
];

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const prefix = `${name}=`;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(prefix));

  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

/**
 * Backend requests always carry the HttpOnly session cookie. State-changing
 * requests echo the readable CSRF cookie in a header (double submit).
 */
async function apiFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) {
      headers.set("X-CSRF-Token", csrf);
    }
  }

  return fetch(input, { ...init, headers, credentials: "include" }).then(
    (response) => {
      if (
        response.status === 401 &&
        typeof window !== "undefined" &&
        !AUTH_PATHS.some((path) => input.includes(path))
      ) {
        window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      }
      return response;
    },
  );
}

export type UserRole = "admin" | "user";

export type UserProfile = {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type LoginInput = {
  email: string;
  password: string;
};

export type RegisterInput = {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
};

export async function fetchCurrentUser(
  signal?: AbortSignal,
): Promise<UserProfile> {
  const response = await apiFetch(`${getApiUrl()}/api/auth/me`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as UserProfile;
}

export async function loginUser(input: LoginInput): Promise<UserProfile> {
  const response = await apiFetch(`${getApiUrl()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as UserProfile;
}

export async function registerUser(input: RegisterInput): Promise<UserProfile> {
  const response = await apiFetch(`${getApiUrl()}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as UserProfile;
}

export async function logoutUser(): Promise<void> {
  const response = await apiFetch(`${getApiUrl()}/api/auth/logout`, {
    method: "POST",
    cache: "no-store",
  });
  if (!response.ok && response.status !== 401) {
    throw new ApiError(await readApiError(response), response.status);
  }
}

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function messageFromError(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date);
}

function getApiUrl(): string {
  if (!apiUrl) {
    throw new Error(configurationError ?? "The backend URL is not configured.");
  }

  return apiUrl;
}

async function readApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };

    if (typeof body.detail === "string") {
      return body.detail;
    }

    if (Array.isArray(body.detail)) {
      return "Please check the submitted fields.";
    }
  } catch {
    // Use the generic message below when the response is not JSON.
  }

  return `The request failed with HTTP ${response.status}.`;
}

export async function fetchIdeas(signal?: AbortSignal): Promise<Idea[]> {
  const response = await apiFetch(`${getApiUrl()}/api/ideas`, {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as Idea[];
}

export async function fetchIdea(
  ideaId: number | string,
  signal?: AbortSignal,
): Promise<Idea> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}`,
    {
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as Idea;
}

export async function createIdea(idea: IdeaInput): Promise<Idea> {
  const response = await apiFetch(`${getApiUrl()}/api/ideas`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(idea),
  });

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as Idea;
}

export async function updateIdea(
  ideaId: number | string,
  idea: IdeaInput,
): Promise<Idea> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(idea),
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as Idea;
}

export async function deleteIdea(ideaId: number | string): Promise<void> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
}

function assessmentUrl(ideaId: number | string, action: string): string {
  return `${getApiUrl()}/api/ideas/${encodeURIComponent(
    String(ideaId),
  )}/assessment/${action}`;
}

async function postAssessment<T>(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await apiFetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as T;
}

export async function prepareAssessment(
  ideaId: number | string,
  signal?: AbortSignal,
): Promise<PrepareAssessmentResponse> {
  const response = await apiFetch(assessmentUrl(ideaId, "prepare"), {
    method: "POST",
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as PrepareAssessmentResponse;
}

export async function refineAssessment(
  ideaId: number | string,
  analysis: AssessmentAnalysis,
  answers: ClarificationAnswer[],
  signal?: AbortSignal,
): Promise<RefinedIdea> {
  return postAssessment<RefinedIdea>(
    assessmentUrl(ideaId, "refine"),
    { analysis, answers },
    signal,
  );
}

export async function scoreAssessment(
  ideaId: number | string,
  input: ScoreAssessmentInput,
  signal?: AbortSignal,
): Promise<AssessmentResult> {
  return postAssessment<AssessmentResult>(
    assessmentUrl(ideaId, "score"),
    input,
    signal,
  );
}

export async function fetchAssessments(
  ideaId: number | string,
  signal?: AbortSignal,
): Promise<AssessmentResult[]> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(
      String(ideaId),
    )}/assessments`,
    {
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as AssessmentResult[];
}

export async function startImprovementSession(
  ideaId: number | string,
  signal?: AbortSignal,
): Promise<ImprovementSession> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}/improvement/session`,
    {
      method: "POST",
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as ImprovementSession;
}

export async function fetchActiveImprovementSession(
  ideaId: number | string,
  signal?: AbortSignal,
): Promise<ImprovementSessionDetail | null> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}/improvement/session/active`,
    {
      cache: "no-store",
      signal,
    },
  );

  if (response.status === 204) {
    return null;
  }

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as ImprovementSessionDetail | null;
}

export async function requestImprovementProposal(
  ideaId: number | string,
  sessionId: number,
  signal?: AbortSignal,
): Promise<ImprovementProposal> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}/improvement/session/${sessionId}/propose`,
    {
      method: "POST",
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as ImprovementProposal;
}

export async function actOnImprovementProposal(
  ideaId: number | string,
  sessionId: number,
  proposalId: number,
  action: "accept" | "reject" | "regenerate",
  signal?: AbortSignal,
): Promise<ProposalActionResponse> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}/improvement/session/${sessionId}/proposals/${proposalId}/action`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ action }),
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as ProposalActionResponse;
}

export async function stopImprovementSession(
  ideaId: number | string,
  sessionId: number,
  signal?: AbortSignal,
): Promise<ImprovementSession> {
  const response = await apiFetch(
    `${getApiUrl()}/api/ideas/${encodeURIComponent(String(ideaId))}/improvement/session/${sessionId}/stop`,
    {
      method: "POST",
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }

  return (await response.json()) as ImprovementSession;
}

// ─────────────────────────────────────────────────────────────────────────────
// Quick Access — Web Shortcuts
// ─────────────────────────────────────────────────────────────────────────────

export type WebShortcut = {
  id: number;
  name: string;
  url: string;
  category: string;
  created_at: string;
  updated_at: string;
};

export type WebShortcutCreate = {
  name: string;
  url: string;
  category?: string;
};

export async function fetchShortcuts(signal?: AbortSignal): Promise<WebShortcut[]> {
  const response = await apiFetch(`${getApiUrl()}/api/shortcuts`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebShortcut[];
}

export async function createShortcut(
  data: WebShortcutCreate,
  signal?: AbortSignal,
): Promise<WebShortcut> {
  const response = await apiFetch(`${getApiUrl()}/api/shortcuts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebShortcut;
}

export async function updateShortcut(
  id: number,
  data: WebShortcutCreate,
  signal?: AbortSignal,
): Promise<WebShortcut> {
  const response = await apiFetch(`${getApiUrl()}/api/shortcuts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebShortcut;
}

export async function deleteShortcut(
  id: number,
  signal?: AbortSignal,
): Promise<void> {
  const response = await apiFetch(`${getApiUrl()}/api/shortcuts/${id}`, {
    method: "DELETE",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Quick Access — Local Helper (port 8001, 127.0.0.1 only)
// ─────────────────────────────────────────────────────────────────────────────

export type HelperApplication = {
  id: string;
  name: string;
  description: string;
  executable: string;
  args: string[];
};

export type HelperApplicationInput = {
  name: string;
  description: string;
  executable: string;
  args: string[];
};

export type HelperProject = {
  id: string;
  name: string;
  description: string;
  working_directory: string;
  executable: string;
  args: string[];
  development_command: string;
  local_url?: string | null;
  status: "running" | "stopped" | "error";
  pid?: number | null;
};

export type HelperProjectInput = {
  name: string;
  description: string;
  working_directory: string;
  executable: string;
  args: string[];
  local_url?: string | null;
};

const HELPER_URL = "http://127.0.0.1:8001";
// NOTE: Token is intentionally stored in the frontend bundle because this tool
// only binds to 127.0.0.1 and is for personal local use. It is not a secret.
const HELPER_TOKEN = "ideon-local-secure-token-2026";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isHelperApplication(value: unknown): value is HelperApplication {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.name) &&
    typeof value.description === "string" &&
    typeof value.executable === "string" &&
    value.executable.trim().length > 0 &&
    isStringList(value.args)
  );
}

function isHelperProject(value: unknown): value is HelperProject {
  return (
    isRecord(value) &&
    isNonEmptyString(value.id) &&
    isNonEmptyString(value.name) &&
    typeof value.description === "string" &&
    typeof value.working_directory === "string" &&
    typeof value.executable === "string" &&
    value.executable.trim().length > 0 &&
    isStringList(value.args) &&
    typeof value.development_command === "string" &&
    (value.local_url === undefined ||
      value.local_url === null ||
      typeof value.local_url === "string") &&
    (value.status === "running" ||
      value.status === "stopped" ||
      value.status === "error") &&
    (value.pid === undefined ||
      value.pid === null ||
      typeof value.pid === "number")
  );
}

/**
 * The helper returns bare lists for `/applications` and `/projects`. Accept a
 * wrapped object too for compatibility, but always validate the payload before
 * it reaches component state.
 */
function parseHelperList<T>(
  data: unknown,
  key: "applications" | "projects",
  isValid: (value: unknown) => value is T,
): T[] {
  const raw = Array.isArray(data)
    ? data
    : isRecord(data)
      ? data[key]
      : undefined;

  if (!Array.isArray(raw)) {
    throw new Error(`Ideon Helper returned an unexpected ${key} response.`);
  }

  return raw.map((item, index) => {
    if (!isValid(item)) {
      throw new Error(
        `Ideon Helper returned an invalid ${key} entry at index ${index}.`,
      );
    }

    return item;
  });
}

async function helperGet<T>(path: string): Promise<T> {
  const response = await fetch(`${HELPER_URL}${path}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Helper error ${response.status}`);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("Ideon Helper returned a response that is not valid JSON.");
  }
}

async function helperPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${HELPER_URL}${path}`, {
    method: "POST",
    headers: {
      "X-Helper-Token": HELPER_TOKEN,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    const parsed = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);
    const message =
      isRecord(parsed) && typeof parsed.error === "string"
        ? parsed.error
        : `Helper error ${response.status}`;
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function fetchHelperHealth(): Promise<boolean> {
  try {
    await helperGet<{ status: string }>("/health");
    return true;
  } catch {
    return false;
  }
}

export async function fetchHelperApplications(): Promise<HelperApplication[]> {
  const data = await helperGet<unknown>("/applications");
  return parseHelperList(data, "applications", isHelperApplication);
}

export async function createHelperApplication(
  input: HelperApplicationInput,
): Promise<void> {
  await helperPost<unknown>("/applications", input);
}

export async function updateHelperApplication(
  id: string,
  input: HelperApplicationInput,
): Promise<void> {
  await helperPost<unknown>(
    `/applications/${encodeURIComponent(id)}/update`,
    input,
  );
}

export async function deleteHelperApplication(id: string): Promise<void> {
  await helperPost<unknown>(`/applications/${encodeURIComponent(id)}/delete`);
}

export async function launchApplication(id: string): Promise<void> {
  await helperPost<{ success: boolean }>(`/applications/${encodeURIComponent(id)}/launch`);
}

export async function fetchHelperProjects(): Promise<HelperProject[]> {
  const data = await helperGet<unknown>("/projects");
  return parseHelperList(data, "projects", isHelperProject);
}

export async function createHelperProject(
  input: HelperProjectInput,
): Promise<void> {
  await helperPost<unknown>("/projects", input);
}

export async function updateHelperProject(
  id: string,
  input: HelperProjectInput,
): Promise<void> {
  await helperPost<unknown>(
    `/projects/${encodeURIComponent(id)}/update`,
    input,
  );
}

export async function deleteHelperProject(id: string): Promise<void> {
  await helperPost<unknown>(`/projects/${encodeURIComponent(id)}/delete`);
}

export async function startProject(
  id: string,
): Promise<{ success: boolean; error?: string }> {
  try {
    const data = await helperPost<{ success: boolean; error?: string }>(
      `/projects/${encodeURIComponent(id)}/start`,
    );
    return data;
  } catch (e: unknown) {
    return { success: false, error: e instanceof Error ? e.message : "Unknown error" };
  }
}

export async function stopProject(
  id: string,
): Promise<{ success: boolean; error?: string }> {
  try {
    const data = await helperPost<{ success: boolean; error?: string }>(
      `/projects/${encodeURIComponent(id)}/stop`,
    );
    return data;
  } catch (e: unknown) {
    return { success: false, error: e instanceof Error ? e.message : "Unknown error" };
  }
}

export async function getProjectStatus(
  id: string,
): Promise<{ status: string; pid?: number }> {
  return helperGet<{ status: string; pid?: number }>(
    `/projects/${encodeURIComponent(id)}/status`,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Website Tracker
// ─────────────────────────────────────────────────────────────────────────────

export type WebsiteActivityStatus = "planned" | "completed";

export const WEBSITE_ACTIVITY_TYPES = [
  "SEO Update",
  "Content Update",
  "CTA Update",
  "Technical Fix",
  "Internal Linking",
  "Other",
] as const;

export type WebsiteActivityType = (typeof WEBSITE_ACTIVITY_TYPES)[number];

export type Website = {
  id: number;
  name: string;
  domain: string;
  created_at: string;
  updated_at: string;
  url_count: number;
  activity_count: number;
};

export type WebsiteUrl = {
  id: number;
  website_id: number;
  website_name: string;
  website_domain: string;
  url: string;
  sitemap_last_modified: string | null;
  created_at: string;
  updated_at: string;
  activity_count: number;
  planned_count: number;
  completed_count: number;
  last_activity_date: string | null;
};

export type WebsiteActivity = {
  id: number;
  title: string;
  description: string;
  activity_type: string;
  status: WebsiteActivityStatus;
  website_id: number;
  website_name: string | null;
  website_url_id: number | null;
  website_url: string | null;
  planned_date: string;
  completed_date: string | null;
  created_at: string;
  updated_at: string;
};

export type WebsiteUrlDetail = WebsiteUrl & {
  activities: WebsiteActivity[];
};

export type WebsiteActivityInput = {
  title: string;
  description: string;
  activity_type: string;
  status: WebsiteActivityStatus;
  website_id?: number | null;
  website_url_id: number | null;
  planned_date: string;
  completed_date?: string | null;
};

export type WebsiteActivityUpdate = Partial<WebsiteActivityInput>;

export type SitemapImportSummary = {
  website_id: number;
  website_name: string;
  filenames: string[];
  files_processed: number;
  found: number;
  imported: number;
  updated: number;
  skipped: number;
  duplicates: number;
  invalid: number;
  unrelated_domains: number;
  sitemap_index: boolean;
  child_sitemaps_skipped: number;
};

export type SitemapFile = {
  filename: string;
};

function trackerQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

export async function fetchWebsites(
  signal?: AbortSignal,
): Promise<Website[]> {
  const response = await apiFetch(`${getApiUrl()}/api/website-tracker/websites`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as Website[];
}

export async function fetchWebsiteUrls(
  params: {
    websiteId?: number;
    search?: string;
    status?: string;
    sort?: string;
    order?: string;
  } = {},
  signal?: AbortSignal,
): Promise<WebsiteUrl[]> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/urls${trackerQuery({
      website_id: params.websiteId,
      search: params.search,
      status_filter: params.status,
      sort: params.sort,
      order: params.order,
    })}`,
    { cache: "no-store", signal },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteUrl[];
}

export async function fetchWebsiteUrl(
  urlId: number | string,
  websiteId?: number,
  signal?: AbortSignal,
): Promise<WebsiteUrlDetail> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/urls/${encodeURIComponent(
      String(urlId),
    )}${trackerQuery({ website_id: websiteId })}`,
    { cache: "no-store", signal },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteUrlDetail;
}

export async function fetchWebsiteUrlActivities(
  urlId: number | string,
  signal?: AbortSignal,
): Promise<WebsiteActivity[]> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/urls/${encodeURIComponent(
      String(urlId),
    )}/activities`,
    { cache: "no-store", signal },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteActivity[];
}

export async function fetchWebsiteActivities(
  params: {
    start?: string;
    end?: string;
    status?: string;
    activityType?: string;
    websiteId?: number;
    websiteUrlId?: number;
  } = {},
  signal?: AbortSignal,
): Promise<WebsiteActivity[]> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/activities${trackerQuery({
      start: params.start,
      end: params.end,
      status_filter: params.status,
      activity_type: params.activityType,
      website_id: params.websiteId,
      website_url_id: params.websiteUrlId,
    })}`,
    { cache: "no-store", signal },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteActivity[];
}

export async function createWebsiteActivity(
  input: WebsiteActivityInput,
): Promise<WebsiteActivity> {
  const response = await apiFetch(`${getApiUrl()}/api/website-tracker/activities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteActivity;
}

export async function updateWebsiteActivity(
  activityId: number,
  updates: WebsiteActivityUpdate,
): Promise<WebsiteActivity> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/activities/${activityId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
      cache: "no-store",
    },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteActivity;
}

export async function deleteWebsiteActivity(activityId: number): Promise<void> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/activities/${activityId}`,
    { method: "DELETE", cache: "no-store" },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
}

export async function completeWebsiteActivity(
  activityId: number,
  completedDate?: string,
): Promise<WebsiteActivity> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/activities/${activityId}/complete`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed_date: completedDate ?? null }),
      cache: "no-store",
    },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as WebsiteActivity;
}

export async function fetchSitemapFiles(
  signal?: AbortSignal,
): Promise<SitemapFile[]> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/sitemaps`,
    { cache: "no-store", signal },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as SitemapFile[];
}

export async function importSitemaps(
  websiteId: number,
  filenames: string[],
): Promise<SitemapImportSummary> {
  const response = await apiFetch(
    `${getApiUrl()}/api/website-tracker/sitemaps/import`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ website_id: websiteId, filenames }),
      cache: "no-store",
    },
  );
  if (!response.ok) {
    throw new ApiError(await readApiError(response), response.status);
  }
  return (await response.json()) as SitemapImportSummary;
}
