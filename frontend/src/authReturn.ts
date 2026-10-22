type RouteStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const VALID_STUDIO_PATH =
  /^\/#\/studio(?:\/(?:connections|history|bots\/(?:new|[a-f0-9]{32}(?:\/edit)?)|runs\/[a-f0-9]{32}))?\/?$/;

export function prepareAuthRoute(
  location: Pick<Location, "hash" | "pathname" | "search">,
  history: Pick<History, "replaceState">,
  storage: RouteStorage | null,
  scope: string,
): string {
  const key = `axelyn.auth-return:${scope}`;
  if (location.hash.startsWith("#/studio")) {
    const requested = `/${location.hash}`;
    const redirect = VALID_STUDIO_PATH.test(requested) ? requested : "/#/studio";
    try {
      storage?.setItem(key, redirect);
    } catch {
      /* The current sign-in can still return without storage. */
    }
    // Clerk owns the hash while signed out. App routes resume after authentication.
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    return redirect;
  }
  try {
    const saved = storage?.getItem(key);
    return saved && VALID_STUDIO_PATH.test(saved) ? saved : "/";
  } catch {
    return "/";
  }
}

export function clearAuthReturn(storage: RouteStorage | null, scope: string) {
  try {
    storage?.removeItem(`axelyn.auth-return:${scope}`);
  } catch {
    /* Storage is optional. */
  }
}
