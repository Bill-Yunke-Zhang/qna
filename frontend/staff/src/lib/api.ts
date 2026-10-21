const BASE = '/api';

// Declares this app's surface on every request — see the matching comment
// in frontend/student/src/lib/api.ts. "staff" does not grant anything by
// itself; the backend still resolves the caller's real course role first
// and only ever clamps toward STUDENT, never the reverse.
const APP_SURFACE = 'staff';

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  // A FormData body (file uploads) sets its own multipart Content-Type.
  const isForm = opts.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      'X-App-Surface': APP_SURFACE,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...((opts.headers as Record<string, string>) ?? {}),
    },
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as {
      message?: string;
      detail?: { msg?: string }[];
    };
    // Schema validation errors (422) carry a `detail` list instead of a message.
    const detail = Array.isArray(err.detail)
      ? err.detail.map((d) => d.msg).filter(Boolean).join('; ')
      : '';
    throw new Error(err.message ?? (detail || `HTTP ${res.status}`));
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
  // Multipart forms, for file uploads.
  postForm: <T>(path: string, form: FormData) => apiFetch<T>(path, { method: 'POST', body: form }),
  putForm: <T>(path: string, form: FormData) => apiFetch<T>(path, { method: 'PUT', body: form }),
};
