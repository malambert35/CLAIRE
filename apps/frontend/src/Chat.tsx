import { useEffect, useRef, useState, type FormEvent } from "react";
import Markdown from "react-markdown";
import { api, type Identity } from "./api";
import "./chat.css";

type Conversation = { id: string; title: string };
type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: string;
  model: string | null;
};
const copy = {
  en: {
    new: "New conversation",
    model: "Local model",
    send: "Send",
    stop: "Stop",
    message: "Your message",
    intro: "What would you like to talk about?",
    local: "Ollama · local inference",
    context:
      "General model knowledge and this conversation only. Family archives are not sent to the model.",
    privacy: "Private conversation. To preserve a memory, use Family Memories.",
    thinking: "CLAIRE is responding…",
    interrupted: "This response is incomplete.",
    stopped: "Generation stopped. Reload to check saved partial responses.",
    older: "Older messages",
    more: "More conversations",
    refresh: "Refresh",
    you: "You",
    saved: "Response saved.",
    noModels: "No local models available.",
  },
  fr: {
    new: "Nouvelle conversation",
    model: "Modèle local",
    send: "Envoyer",
    stop: "Arrêter",
    message: "Votre message",
    intro: "De quoi souhaitez-vous parler ?",
    local: "Ollama · traitement local",
    context:
      "Connaissances générales du modèle et cette conversation uniquement. Les archives familiales ne sont pas envoyées au modèle.",
    privacy:
      "Conversation privée. Pour conserver un souvenir, utilisez Souvenirs de famille.",
    thinking: "CLAIRE répond…",
    interrupted: "Cette réponse est incomplète.",
    stopped:
      "Génération arrêtée. Actualisez pour consulter les éventuelles réponses partielles enregistrées.",
    older: "Messages précédents",
    more: "Autres conversations",
    refresh: "Actualiser",
    you: "Vous",
    saved: "Réponse enregistrée.",
    noModels: "Aucun modèle local disponible.",
  },
};

export function Chat({ user, lang }: { user: Identity; lang: "en" | "fr" }) {
  const t = copy[lang];
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [draft, setDraft] = useState("");
  const [live, setLive] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [hasOlder, setHasOlder] = useState(false);
  const [more, setMore] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);
  const canSend = ["member", "family_admin"].includes(user.role);
  async function loadModels() {
    setError("");
    try {
      const data = await api<{ models: string[]; default_model: string }>(
        "/ai/models",
      );
      setModels(data.models);
      setModel(data.default_model);
      if (!data.models.length) setError(t.noModels);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function loadList(offset = 0) {
    const data = await api<Conversation[]>(`/conversations?offset=${offset}`);
    setConversations((existing) => (offset ? [...existing, ...data] : data));
    setMore(data.length === 50);
  }
  useEffect(() => {
    loadModels();
    loadList().catch((e) => setError(e.message));
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [live, messages]);
  async function open(conversation: Conversation, older = false) {
    setError("");
    setSaved(false);
    setBusy(true);
    try {
      const data = await api<{ messages: Message[]; has_older: boolean }>(
        `/conversations/${conversation.id}?before=${older ? messages.length : 0}`,
      );
      setCurrent(conversation);
      setMessages((existing) =>
        older ? [...data.messages, ...existing] : data.messages,
      );
      setHasOlder(data.has_older);
      setLive("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || !model || busy) return;
    const content = draft.trim();
    setBusy(true);
    setError("");
    setLive("");
    setSaved(false);
    const abort = new AbortController();
    controller.current = abort;
    try {
      let conversation = current;
      if (!conversation) {
        conversation = await api<Conversation>("/conversations", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": user.csrf_token,
          },
          body: JSON.stringify({ title: content.slice(0, 120) }),
          signal: abort.signal,
        });
        setCurrent(conversation);
        setConversations((existing) => [conversation!, ...existing]);
      }
      const response = await fetch(
        `/api/v1/conversations/${conversation.id}/messages`,
        {
          method: "POST",
          credentials: "same-origin",
          signal: abort.signal,
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": user.csrf_token,
          },
          body: JSON.stringify({ content, model }),
        },
      );
      if (!response.ok) {
        const problem = await response.json();
        throw new Error(
          typeof problem.detail === "string"
            ? problem.detail
            : "Request failed",
        );
      }
      if (!response.body) throw new Error("No response stream");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let done = false;
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const kind = frame
            .split("\n")
            .find((line) => line.startsWith("event: "))
            ?.slice(7);
          const payload = JSON.parse(
            frame
              .split("\n")
              .find((line) => line.startsWith("data: "))
              ?.slice(6) ?? "{}",
          );
          if (kind === "start") {
            setMessages((existing) => [...existing, payload.message]);
            setDraft("");
          }
          if (kind === "token") setLive((value) => value + payload.text);
          if (kind === "done") {
            setMessages((existing) => [...existing, payload.message]);
            setLive("");
            setSaved(true);
            done = true;
          }
          if (kind === "error") throw new Error(payload.detail);
        }
      }
      if (!done) throw new Error(t.interrupted);
    } catch (e) {
      setError(
        (e as Error).name === "AbortError" ? t.stopped : (e as Error).message,
      );
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }
  return (
    <section className="chat-panel">
      <div className="chat-history">
        <button
          disabled={busy}
          className="primary"
          onClick={() => {
            setCurrent(null);
            setMessages([]);
            setLive("");
            setError("");
            setSaved(false);
            setHasOlder(false);
          }}
        >
          {t.new}
        </button>
        <nav aria-label={t.more}>
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              aria-current={
                current?.id === conversation.id ? "page" : undefined
              }
              disabled={busy}
              onClick={() => open(conversation)}
            >
              {conversation.title}
            </button>
          ))}
        </nav>
        {more && (
          <button
            disabled={busy}
            onClick={() =>
              loadList(conversations.length).catch((e) => setError(e.message))
            }
          >
            {t.more}
          </button>
        )}
      </div>
      <div className="chat-main">
        <div className="chat-provider">
          <strong>{t.local}</strong>
          <label>
            {t.model}
            <select
              aria-label={t.model}
              value={model}
              onChange={(event) => setModel(event.target.value)}
              disabled={busy || !models.length}
            >
              {models.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          <button disabled={busy} onClick={loadModels}>
            {t.refresh}
          </button>
        </div>
        <p className="chat-context">{t.context}</p>
        {error && <p role="alert">{error}</p>}
        {saved && <p role="status">{t.saved}</p>}
        <div className="chat-messages">
          {hasOlder && current && (
            <button disabled={busy} onClick={() => open(current, true)}>
              {t.older}
            </button>
          )}
          {!messages.length && !live && <h2>{t.intro}</h2>}
          {messages.map((message) => (
            <article
              key={message.id}
              className={`chat-message ${message.role}`}
            >
              <strong>
                {message.role === "user"
                  ? t.you
                  : `CLAIRE · ${message.model ?? model}`}
              </strong>
              <div className="markdown">
                <Markdown
                  skipHtml
                  components={{ img: ({ alt }) => <span>[{alt}]</span> }}
                >
                  {message.content}
                </Markdown>
              </div>
              {message.status !== "complete" && <p>{t.interrupted}</p>}
            </article>
          ))}
          {live && (
            <article className="chat-message assistant">
              <strong>CLAIRE · {model}</strong>
              <div className="markdown">
                <Markdown
                  skipHtml
                  components={{ img: ({ alt }) => <span>[{alt}]</span> }}
                >
                  {live}
                </Markdown>
              </div>
            </article>
          )}
          <div ref={bottom} />
        </div>
        <form className="chat-composer" onSubmit={send}>
          <label>
            {t.message}
            <textarea
              aria-label={t.message}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              maxLength={4000}
              rows={3}
              disabled={busy || !canSend}
              required
            />
          </label>
          <div>
            {busy ? (
              <button type="button" onClick={() => controller.current?.abort()}>
                {t.stop}
              </button>
            ) : (
              <button
                className="primary"
                disabled={!model || !draft.trim() || !canSend}
              >
                {t.send}
              </button>
            )}
          </div>
        </form>
        {busy && <p role="status">{t.thinking}</p>}
        <small>{t.privacy}</small>
      </div>
    </section>
  );
}
