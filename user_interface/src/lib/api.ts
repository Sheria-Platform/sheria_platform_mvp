import { getAuthToken } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FetchOptions extends RequestInit {
  skipAuth?: boolean;
}

export async function apiFetch<T>(
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const { skipAuth, ...fetchOptions } = options;
  const token = skipAuth ? null : getAuthToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
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
  const token = getAuthToken();
  const url = path.startsWith("http")
    ? path
    : `${API_BASE}${path}`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    throw new Error(`Stream error: HTTP ${res.status}`);
  }

  return res;
}
