import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, BookOpen, FileText, Files, MessageSquare, PanelLeft, Plus, SquarePen, X } from "lucide-react";
import { askQuestion, deleteDocument, getDocuments, indexDocument, uploadDocument } from "./api";
import { readChats, saveChats } from "./chats";
import AnswerCard from "./components/AnswerCard";
import DocumentPanel from "./components/DocumentPanel";
import QuestionInput from "./components/QuestionInput";
import type { Chat, ChatMessage, DocumentLibrary, UploadedDocument } from "./types";

const INITIAL_CHATS = readChats();
const SUGGESTIONS = [
  { label: "Explain the refund process", question: "What is the refund approval process for damaged goods?" },
  { label: "Handle a delayed delivery", question: "When should a delivery delay be escalated?" },
  { label: "Check the AI usage policy", question: "Can staff paste invoice data into ChatGPT?" },
];

export default function App() {
  const [chats, setChats] = useState<Chat[]>(INITIAL_CHATS);
  const [activeId, setActiveId] = useState<string | null>(INITIAL_CHATS[0]?.id ?? null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 900);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [library, setLibrary] = useState<DocumentLibrary | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [busyDocument, setBusyDocument] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const active = chats.find((chat) => chat.id === activeId);
  const messages = active?.messages ?? [];

  useEffect(() => { saveChats(chats); }, [chats]);
  useEffect(() => { void getDocuments().then(setLibrary).catch((error: Error) => setLibraryError(error.message)); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, asking]);
  useEffect(() => {
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape" && !documentsOpen && window.innerWidth <= 900) setSidebarOpen(false);
    }
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [documentsOpen]);

  function newChat() { setActiveId(null); setQuestion(""); if (window.innerWidth <= 900) setSidebarOpen(false); }

  function updateMessage(chatId: string, messageId: string, update: Partial<ChatMessage>) {
    setChats((current) => current.map((chat) => chat.id === chatId ? {
      ...chat, messages: chat.messages.map((message) => message.id === messageId ? { ...message, ...update } : message),
    } : chat));
  }

  async function submit(nextQuestion = question) {
    const text = nextQuestion.trim(); if (text.length < 3 || asking) return;
    const chatId = activeId ?? crypto.randomUUID(); const assistantId = crypto.randomUUID();
    const additions: ChatMessage[] = [
      { id: crypto.randomUUID(), role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", pending: true },
    ];
    const history = messages.filter((message) => !message.pending && !message.error).slice(-6)
      .map(({ role, content }) => ({ role, content: content.slice(0, 5000) }));
    setActiveId(chatId); setQuestion(""); setAsking(true);
    setChats((current) => {
      const existing = current.find((chat) => chat.id === chatId);
      const next: Chat = existing ? { ...existing, messages: [...existing.messages, ...additions], updatedAt: Date.now() }
        : { id: chatId, title: text, updatedAt: Date.now(), messages: additions };
      return [next, ...current.filter((chat) => chat.id !== chatId)].slice(0, 20);
    });
    try {
      const response = await askQuestion(text, history);
      updateMessage(chatId, assistantId, { content: response.answer, response, pending: false });
    } catch (error) {
      updateMessage(chatId, assistantId, { pending: false, error: error instanceof Error ? error.message : "Unable to answer. Try again." });
    } finally { setAsking(false); }
  }

  function updateDocument(document: UploadedDocument) {
    setLibrary((current) => current && ({ ...current,
      documents: [document, ...current.documents.filter((doc) => doc.id !== document.id)],
    }));
  }
  function pickFiles() { setDocumentsOpen(true); fileInput.current?.click(); }
  async function uploadFiles(files: File[]) {
    if (!files.length || uploading) return;
    setDocumentsOpen(true); setLibraryError(null); const errors: string[] = [];
    for (const file of files) {
      if (!/\.(pdf|md)$/i.test(file.name)) { errors.push(`${file.name}: choose a PDF or Markdown file.`); continue; }
      if (file.size > 10 * 1024 * 1024) { errors.push(`${file.name}: the limit is 10 MB.`); continue; }
      setUploading(file.name);
      try { updateDocument(await uploadDocument(file)); }
      catch (error) { errors.push(error instanceof Error ? `${file.name}: ${error.message}` : `Unable to upload ${file.name}.`); }
    }
    setUploading(null); setLibraryError(errors.length ? errors.join(" ") : null);
    if (fileInput.current) fileInput.current.value = "";
  }
  async function retryIndex(id: string) {
    setBusyDocument(id); setLibraryError(null);
    try { updateDocument(await indexDocument(id)); }
    catch (error) { setLibraryError(error instanceof Error ? error.message : "Unable to index document."); }
    finally { setBusyDocument(null); }
  }
  async function removeDocument(id: string) {
    const doc = library?.documents.find((item) => item.id === id);
    if (!doc || !window.confirm(`Remove ${doc.filename} from this workspace?`)) return;
    setBusyDocument(id); setLibraryError(null);
    try {
      await deleteDocument(id);
      setLibrary((current) => current && ({ ...current, documents: current.documents.filter((item) => item.id !== id) }));
    } catch (error) { setLibraryError(error instanceof Error ? error.message : "Unable to remove document."); }
    finally { setBusyDocument(null); }
  }

  const composer = <QuestionInput value={question} loading={asking} uploading={!!uploading}
    onChange={setQuestion} onSubmit={() => void submit()} onAttach={pickFiles} />;

  return (
    <div className={`app-shell ${sidebarOpen ? "sidebar-open" : ""}`}>
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />}
      <aside className="sidebar" aria-label="Sidebar" aria-hidden={!sidebarOpen}>
        <div className="sidebar-brand"><span className="brand-symbol"><Files size={21} /></span><strong>Sentral</strong>
          <button className="icon-button sidebar-close" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)}><X size={18} /></button></div>
        <nav className="primary-nav">
          <button onClick={newChat}><SquarePen size={18} />New chat<span className="shortcut" aria-hidden="true">↗</span></button>
          <button onClick={() => { setDocumentsOpen(true); if (window.innerWidth <= 900) setSidebarOpen(false); }}>
            <BookOpen size={18} />Documents<span className="document-count">{library?.documents.length ?? 0}</span></button>
        </nav>
        <div className="recent-heading">Recent chats</div>
        <nav className="chat-history" aria-label="Recent chats">
          {chats.length ? chats.map((chat) => <button key={chat.id} className={activeId === chat.id ? "active" : ""}
            title={chat.title} onClick={() => { setActiveId(chat.id); setQuestion(""); if (window.innerWidth <= 900) setSidebarOpen(false); }}>
            <MessageSquare size={15} /><span>{chat.title}</span></button>) : <p className="no-chats">Your conversations will appear here.</p>}
        </nav>
        <div className="sidebar-footer"><span className="axelyn-mark">A</span><div><strong>Axelyn</strong><span>Proof Lab</span></div></div>
      </aside>
      <main className="main-workspace">
        <header className="workspace-header"><div>
          <button className="icon-button" aria-label={sidebarOpen ? "Hide sidebar" : "Open sidebar"}
            onClick={() => setSidebarOpen(!sidebarOpen)}><PanelLeft size={20} /></button>
          <h1>Sentral <span>Ops assistant</span></h1></div>
          <button className="header-documents" onClick={() => setDocumentsOpen(true)}><FileText size={16} /><span>Documents</span></button></header>
        {!messages.length ? <section className="empty-chat">
          <div className="welcome"><h2>What would you like to know?</h2><p>Ask your SOPs. Find the next step.</p></div>
          <div className="composer-container">{composer}</div>
          <div className="suggestions" aria-label="Suggested questions">{SUGGESTIONS.map((item) =>
            <button key={item.label} disabled={asking} onClick={() => void submit(item.question)}>{item.label}<ArrowUpRight size={14} /></button>)}</div>
          <button className="add-document-hint" onClick={pickFiles}><Plus size={15} />Or add a document of your own</button>
        </section> : <>
          <section className="conversation" aria-label="Conversation"><div className="message-column">
            {messages.map((message) => message.role === "user" ? <div className="user-message" key={message.id}><p>{message.content}</p></div>
              : <AnswerCard key={message.id} message={message} />)}<div ref={end} /></div></section>
          <div className="bottom-composer"><div className="composer-container">{composer}</div></div>
        </>}
        <footer className="workspace-footer">Answers from your documents. Check the sources before acting.</footer>
      </main>
      <input ref={fileInput} type="file" className="visually-hidden" tabIndex={-1} accept=".pdf,.md,application/pdf,text/markdown"
        multiple onChange={(event) => void uploadFiles(Array.from(event.target.files ?? []))} aria-label="Choose documents" />
      <DocumentPanel open={documentsOpen} library={library} uploading={uploading} busyId={busyDocument} error={libraryError}
        onClose={() => setDocumentsOpen(false)} onPickFiles={pickFiles} onUpload={(files) => void uploadFiles(files)}
        onRetry={(id) => void retryIndex(id)} onDelete={(id) => void removeDocument(id)} />
    </div>
  );
}
