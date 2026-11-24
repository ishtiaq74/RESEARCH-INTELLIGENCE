/**
 * Single API client module for Research Intelligence frontend.
 *
 * Security & Cookie Architecture:
 * - All requests use `credentials: "include"` so the browser automatically sends
 *   and receives the httpOnly `session` cookie.
 * - Session tokens, IDs, and passwords are NEVER stored in localStorage,
 *   sessionStorage, or JavaScript memory beyond the form inputs.
 * - The session is managed entirely by the server-side session store and the
 *   httpOnly cookie.
 */

export interface UserResponse {
  id: number;
  email: string;
}

export interface ProjectResponse {
  id: number;
  name: string;
  owner_id: number;
  created_at: string;
  updated_at: string;
}

export interface ListProjectsParams {
  limit?: number;
  offset?: number;
}

export class ApiClientError extends Error {
  status: number;
  detail?: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.detail = detail;
  }
}

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

interface ApiRequestOptions extends RequestInit {
  params?: Record<string, string | number | undefined>;
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const { params, headers: customHeaders, ...fetchOptions } = options;

  let url = `${API_BASE_URL}${path}`;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) {
        searchParams.append(key, String(value));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const headers = new Headers(customHeaders);
  if (
    typeof fetchOptions.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers,
      credentials: "include", // Required for SameSite=Lax session cookies
    });
  } catch (err) {
    throw new ApiClientError(
      "Unable to connect to the server. Please ensure the backend is running.",
      0,
      err
    );
  }

  if (!response.ok) {
    let detail: unknown = null;
    let message = "";

    try {
      const data = await response.json();
      detail = data?.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) {
        // FastAPI / Pydantic validation error format
        message = String(detail[0].msg);
      }
    } catch {
      // Body was not JSON or empty
    }

    if (!message) {
      if (response.status === 401) {
        message = "Authentication required. Please sign in.";
      } else if (response.status === 404) {
        message = "Resource not found.";
      } else if (response.status === 409) {
        message = "Email already registered.";
      } else if (response.status === 422) {
        message = "Invalid input. Please check your data.";
      } else if (response.status === 429) {
        message = "Too many requests. Please try again later.";
      } else if (response.status >= 500) {
        message = "Internal server error. Please try again later.";
      } else {
        message = `Request failed with status ${response.status}.`;
      }
    }

    throw new ApiClientError(message, response.status, detail);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Auth functions
// ---------------------------------------------------------------------------

export async function register(
  email: string,
  password: string
): Promise<UserResponse> {
  return apiRequest<UserResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(
  email: string,
  password: string
): Promise<UserResponse> {
  return apiRequest<UserResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  return apiRequest<void>("/auth/logout", {
    method: "POST",
  });
}

export async function getMe(): Promise<UserResponse> {
  return apiRequest<UserResponse>("/auth/me", {
    method: "GET",
  });
}

export const me = getMe;

// ---------------------------------------------------------------------------
// Projects functions
// ---------------------------------------------------------------------------

export async function listProjects(
  params?: ListProjectsParams
): Promise<ProjectResponse[]> {
  return apiRequest<ProjectResponse[]>("/projects", {
    method: "GET",
    params: {
      limit: params?.limit,
      offset: params?.offset,
    },
  });
}

export async function createProject(name: string): Promise<ProjectResponse> {
  return apiRequest<ProjectResponse>("/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameProject(
  id: number,
  name: string
): Promise<ProjectResponse> {
  return apiRequest<ProjectResponse>(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteProject(id: number): Promise<void> {
  return apiRequest<void>(`/projects/${id}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Documents functions
// ---------------------------------------------------------------------------

/**
 * DocumentRead mirrors the backend DocumentRead schema (D-033).
 * Internal storage fields (stored_filename, sha256, filesystem paths) are
 * intentionally excluded from the API response.
 */
export interface DocumentRead {
  id: number;
  project_id: number;
  original_filename: string;
  size_bytes: number;
  page_count: number | null;
  status: string; // "uploaded" | "processing" | "ready" | "failed"
  created_at: string; // ISO-8601 datetime string
}

/**
 * Maps HTTP error status codes from POST /projects/{id}/documents to
 * user-facing messages.  Error codes are specified in D-031.
 *
 * For 422 we surface the server's detail text because it carries the specific
 * reason (corrupt, encrypted, empty, too many pages, project limit).  For
 * all other codes we return a fixed string to avoid leaking internal detail.
 *
 * Client-side pre-checks (extension, size) already filter the common 413/415
 * cases before the request is sent; this function is the last line of defence
 * and also covers the server-authoritative check.
 */
export function documentUploadErrorMessage(
  err: ApiClientError
): string {
  switch (err.status) {
    case 409:
      return "Already uploaded in this project.";
    case 413:
      return "Larger than 20 MB.";
    case 415:
      return "Not a PDF.";
    case 422:
      // Surface the server's reason (D-031 lists: corrupt, encrypted, empty,
      // too many pages, project document limit reached).
      return err.message || "File rejected by the server.";
    case 404:
      return "Project or document not found.";
    case 401:
      // Caller should redirect to /login; this string is a fallback.
      return "Authentication required. Please sign in.";
    default:
      return err.message || "Upload failed. Please try again.";
  }
}

export async function listDocuments(
  projectId: number
): Promise<DocumentRead[]> {
  return apiRequest<DocumentRead[]>(`/projects/${projectId}/documents`, {
    method: "GET",
  });
}

/**
 * Upload a PDF to a project.
 *
 * Uses FormData with field name "file" (required by the backend multipart
 * parser).  We do NOT set Content-Type manually — the browser must set it
 * so it can include the multipart boundary in the header value.  Setting it
 * manually would omit the boundary and produce a 422 parse error.
 */
export async function uploadDocument(
  projectId: number,
  file: File
): Promise<DocumentRead> {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<DocumentRead>(`/projects/${projectId}/documents`, {
    method: "POST",
    body: form,
  });
}

export async function deleteDocument(
  projectId: number,
  documentId: number
): Promise<void> {
  return apiRequest<void>(
    `/projects/${projectId}/documents/${documentId}`,
    { method: "DELETE" }
  );
}

