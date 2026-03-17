const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FetchOptions extends RequestInit {
  skipAuth?: boolean;
}

export async function apiFetch<T>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { skipAuth: _skipAuth, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  // Authorization is handled server-side via the httpOnly sheria_auth cookie.
  // Calls that reach FastAPI directly must be routed through a Next.js API
  // proxy route (app/api/proxy/...) which reads the httpOnly cookie and adds
  // the Bearer header before forwarding.

  // Paths routed through Next.js (/api/auth/... or /api/proxy/...) are same-origin.
  const url = path.startsWith("http") || path.startsWith("/api/auth") || path.startsWith("/api/proxy")
    ? path
    : `${API_BASE}${path}`;
  const res = await fetch(url, { ...fetchOptions, headers });

  if (!res.ok) {
    // Prefer the human-readable `detail` field from FastAPI JSON error bodies.
    const text = await res.text();
    let message = text || `HTTP ${res.status}`;
    try {
      const json = JSON.parse(text);
      if (json.detail) message = json.detail;
      else if (json.error) message = json.error;
    } catch {
      // body was not JSON — use raw text as-is
    }
    throw new Error(message);
  }

  return res.json() as Promise<T>;
}

export async function apiStream(
  path: string,
  body: unknown,
  signal?: AbortSignal
): Promise<Response> {
  // Proxy paths (/api/proxy/...) are same-origin Next.js routes — never prepend API_BASE.
  const url = path.startsWith("http") || path.startsWith("/api/proxy")
    ? path
    : `${API_BASE}${path}`;

  // Authorization is handled server-side via the httpOnly sheria_auth cookie.
  // Route this call through a Next.js proxy endpoint that forwards the token.
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    throw new Error(`Stream error: HTTP ${res.status}`);
  }

  return res;
}
