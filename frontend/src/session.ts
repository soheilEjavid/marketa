/** Local-storage-backed session for the real login flow. Deliberately a
 * plain module (no React) so api.ts can read/clear it without a React
 * dependency — App.tsx listens for the "marketa:unauthorized" event to
 * react to a session becoming invalid from anywhere in the app.
 */

export type Session = {
  token: string;
  userId: number;
  username: string;
  fullName: string;
  role: string;
};

const SESSION_KEY = "marketa-session";
const UNAUTHORIZED_EVENT = "marketa:unauthorized";

export function getSession(): Session | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<Session>;
    if (!parsed.token || !parsed.userId || !parsed.username || !parsed.role) return null;
    return parsed as Session;
  } catch {
    return null;
  }
}

export function setSession(session: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

/** Dispatched by api.ts whenever any request comes back 401 — App.tsx
 * listens for this to drop back to the login screen from anywhere. */
export function notifyUnauthorized(): void {
  clearSession();
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}

export function onUnauthorized(handler: () => void): () => void {
  window.addEventListener(UNAUTHORIZED_EVENT, handler);
  return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
}
