import type { Chat } from "./types";
function storageKey(scope: string) {
  return `sentral.chats.v2:${scope}`;
}
export function readChats(scope: string): Chat[] {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey(scope)) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value
      .filter(
        (chat) =>
          typeof chat.id === "string" &&
          typeof chat.title === "string" &&
          Array.isArray(chat.messages),
      )
      .slice(0, 20)
      .map((chat: Chat) => ({
        ...chat,
        messages: chat.messages.map((message) =>
          message.pending
            ? {
                ...message,
                pending: false,
                error: "This response was interrupted. Send your question again.",
              }
            : message,
        ),
      }));
  } catch {
    return [];
  }
}
export function saveChats(scope: string, chats: Chat[]): void {
  try {
    localStorage.setItem(storageKey(scope), JSON.stringify(chats.slice(0, 20)));
  } catch {
    /* Chatting still works when browser storage is unavailable. */
  }
}
