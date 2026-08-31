const CSRF_COOKIE_NAME = "csrf_token";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE_NAME}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  // FormData bodies must NOT get an explicit Content-Type -- the browser
  // sets one itself (including the multipart boundary parameter), and
  // overriding it here would break upload parsing on the server.
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  // The CSRF cookie is deliberately readable by JS (not httpOnly) -- that's
  // the double-submit mechanism itself. The session cookie is never touched
  // here; the browser attaches it automatically since every call below stays
  // same-origin (proxied through Next.js per next.config.js), and it's
  // httpOnly regardless, so client code has no way to read it even if it wanted to.
  if (!SAFE_METHODS.has(method)) {
    const csrfToken = readCsrfCookie();
    if (csrfToken) headers.set(CSRF_HEADER_NAME, csrfToken);
  }

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const detail =
      (payload && typeof payload.detail === "string" && payload.detail) ||
      response.statusText ||
      "Something went wrong. Please try again.";
    throw new ApiError(response.status, detail);
  }

  return payload as T;
}

// fetch() has no upload-progress signal at all, so real progress reporting
// needs XMLHttpRequest for this one call -- everything else stays on fetch.
function uploadWithProgress<T>(
  path: string,
  formData: FormData,
  onProgress?: (percent: number) => void
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/v1${path}`);
    xhr.withCredentials = true;

    const csrfToken = readCsrfCookie();
    if (csrfToken) xhr.setRequestHeader(CSRF_HEADER_NAME, csrfToken);

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      let payload: { detail?: string } | null = null;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as T);
      } else {
        reject(new ApiError(xhr.status, payload?.detail || "Upload failed. Please try again."));
      }
    };

    xhr.onerror = () => reject(new ApiError(0, "Upload failed. Please try again."));

    xhr.send(formData);
  });
}

export const apiClient = {
  get: <T,>(path: string) => request<T>(path, { method: "GET" }),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  uploadWithProgress,
};
