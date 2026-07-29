const STORAGE_KEY = "marketa-check-reminder-dismissed";

type DismissRecord = { date: string; signature: string };

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * A reminder is considered dismissed only for the exact same day AND the
 * exact same set of due checks — a new day, or a change in which checks are
 * due soon (new one added, one cleared out), makes it reappear.
 */
export function isReminderDismissed(signature: string): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as Partial<DismissRecord>;
    return parsed.date === todayIso() && parsed.signature === signature;
  } catch {
    return false;
  }
}

export function dismissReminder(signature: string): void {
  try {
    const record: DismissRecord = { date: todayIso(), signature };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // localStorage unavailable (private mode, quota, etc.) — dismissal just
    // won't persist across reloads.
  }
}
