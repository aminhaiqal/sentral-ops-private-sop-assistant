export type PendingGoogleAuth = { flow_id: string; expires_at: number };
const prefix = "axelyn.google-drive.auth:";

export function googleAuthorizationUrl(value: string): string {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.hostname !== "accounts.google.com" ||
    url.port ||
    url.username ||
    url.password ||
    url.pathname !== "/o/oauth2/v2/auth"
  )
    throw new Error("Google returned an invalid authorization link.");
  return url.href;
}
export function pendingGoogleAuth(
  storage: Pick<Storage, "getItem"> | null,
  scope: string,
  now = Date.now(),
): PendingGoogleAuth | null {
  try {
    const item = JSON.parse(storage?.getItem(prefix + scope) ?? "null");
    return item &&
      /^[a-f0-9]{32}$/.test(item.flow_id) &&
      Number.isFinite(item.expires_at) &&
      item.expires_at > now &&
      item.expires_at <= now + 600000
      ? { flow_id: item.flow_id, expires_at: item.expires_at }
      : null;
  } catch {
    return null;
  }
}
export function saveGoogleAuth(
  storage: Pick<Storage, "setItem" | "removeItem"> | null,
  scope: string,
  value: PendingGoogleAuth | null,
) {
  try {
    if (value) storage?.setItem(prefix + scope, JSON.stringify(value));
    else storage?.removeItem(prefix + scope);
  } catch {
    /* Authorization still works in this tab when storage is unavailable. */
  }
}
