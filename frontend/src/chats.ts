import type { Chat } from "./types";
const STORAGE_KEY = "sentral.chats.v1";
export function readChats(): Chat[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((chat) => typeof chat.id === "string" && typeof chat.title === "string"
      && Array.isArray(chat.messages)).slice(0, 20).map((chat: Chat) => ({
        ...chat, messages: chat.messages.map((message) => message.pending ? {
          ...message, pending: false, error: "This response was interrupted. Send your question again.",
        } : message),
      }));
  } catch { return []; }
}
export function saveChats(chats: Chat[]): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(chats.slice(0, 20))); }
  catch { /* Chatting still works when browser storage is unavailable. */ }
}
