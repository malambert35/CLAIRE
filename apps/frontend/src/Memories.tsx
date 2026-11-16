import { useEffect, useState, type FormEvent } from "react";
import Markdown from "react-markdown";
import { api, type Identity } from "./api";
import { memoryText } from "./memoryText";
import "./memories.css";
import { ImportMemory } from "./ImportMemory";
import { ImportDocument } from "./ImportDocument";

type Source = {
  id: string;
  reference: string;
  relationship: "supports" | "contradicts" | "context";
};
export type Memory = {
  id: string;
  title: string;
  content: string;
  visibility: "private" | "family";
  revision: number;
  event_date: string | null;
  recorded_at: string;
  contributor_id: string;
  contributor_label: string | null;
  owner_id: string;
  verification: "recollection" | "verified" | "uncertain" | "ai_interpretation";
  sources: Source[];
  deleted: boolean;
  can_edit: boolean;
};
type Labels = typeof memoryText.en;

function Editor({
  memory,
  t,
  busy,
  onSave,
  onCancel,
}: {
  memory: Memory | null;
  t: Labels;
  busy: boolean;
  onSave: (body: object) => Promise<void>;
  onCancel: () => void;
}) {
  const [visibility, setVisibility] = useState(memory?.visibility ?? "private");
  const [confirmed, setConfirmed] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const reference = String(fields.get("source") ?? "").trim();
    const sources = reference
      ? [
          {
            id: memory?.sources[0]?.id,
            reference,
            relationship: memory?.sources[0]?.relationship ?? "supports",
          },
          ...(memory?.sources.slice(1) ?? []),
        ]
      : (memory?.sources.slice(1) ?? []);
    await onSave({
      title: fields.get("title"),
      content: fields.get("content"),
      visibility,
      event_date: String(fields.get("event") ?? "").trim() || null,
      verification: fields.get("verification"),
      sources,
      confirmed,
      ...(memory ? { expected_revision: memory.revision } : {}),
    });
  }
  return (
    <form
      className="memory-editor"
      onSubmit={submit}
      onChange={(event) => {
        if (!(
          event.target instanceof HTMLInputElement &&
          event.target.name === "confirmed"
        ))
          setConfirmed(false);
      }}
    >
      <h2>{memory ? t.edit : t.new}</h2>
      <label>
        {t.title}
        <input
          name="title"
          defaultValue={memory?.title}
          required
          maxLength={200}
        />
      </label>
      <label>
        {t.content}
        <textarea
          aria-label={t.content}
          name="content"
          defaultValue={memory?.content}
          required
          maxLength={6000}
          rows={10}
        />
      </label>
      <small>{t.markdown}</small>
      <div className="form-columns">
        <label>
          {t.event}
          <input
            name="event"
            defaultValue={memory?.event_date ?? ""}
            maxLength={10}
            placeholder="1962 / 1962-07-14"
          />
        </label>
        <label>
          {t.verification}
          <select
            name="verification"
            defaultValue={memory?.verification ?? "recollection"}
          >
            {(
              [
                "recollection",
                "verified",
                "uncertain",
                "ai_interpretation",
              ] as const
            ).map((value) => (
              <option key={value} value={value}>
                {t[value]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        {t.source}
        <input
          name="source"
          defaultValue={memory?.sources[0]?.reference ?? ""}
          maxLength={2000}
        />
      </label>
      <label>
        {t.visibility}
        <select
          name="visibility"
          value={visibility}
          onChange={(event) =>
            setVisibility(event.target.value as "private" | "family")
          }
        >
          <option value="private">{t.private}</option>
          <option value="family">{t.family}</option>
        </select>
      </label>
      {visibility === "family" && (
        <p className="sharing-notice">{t.sharedNotice}</p>
      )}
      <label className="confirmation">
        <input
          type="checkbox"
          name="confirmed"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
          required
        />
        {t.confirm}
      </label>
      <div className="memory-actions">
        <button type="submit" className="primary" disabled={busy || !confirmed}>
          {busy ? t.working : t.save}
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          {t.cancel}
        </button>
      </div>
    </form>
  );
}

function Story({
  memory,
  t,
  lang,
}: {
  memory: Memory;
  t: Labels;
  lang: string;
}) {
  return (
    <article className="story">
      <h2>{memory.title}</h2>
      <div className="story-meta">
        <span>{memory.visibility === "private" ? t.private : t.family}</span>
        <span>{t[memory.verification]}</span>
        <span>
          {t.revision} {memory.revision}
        </span>
      </div>
      {memory.event_date && <p>{memory.event_date}</p>}
      <div className="markdown">
        <Markdown
          skipHtml
          components={{ img: ({ alt }) => <span>[{alt}]</span> }}
        >
          {memory.content}
        </Markdown>
      </div>
      <dl>
        <dt>{t.recorded}</dt>
        <dd>{new Date(memory.recorded_at).toLocaleString(lang)}</dd>
        <dt>{t.owner}</dt>
        <dd>{memory.contributor_label ?? memory.contributor_id}</dd>
      </dl>
      {memory.sources.length > 0 && (
        <ul>
          {memory.sources.map((source) => (
            <li key={source.id}>
              {source.reference} ({source.relationship})
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function Memories({
  user,
  lang,
  timeline = false,
  documents = false,
}: {
  user: Identity;
  lang: "en" | "fr";
  timeline?: boolean;
  documents?: boolean;
}) {
  const t = memoryText[lang];
  const [items, setItems] = useState<Memory[]>([]);
  const [selected, setSelected] = useState<Memory | null>(null);
  const [editing, setEditing] = useState(false);
  const [trash, setTrash] = useState(false);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<"saved" | "deleted" | "restored" | "">(
    "",
  );
  const [history, setHistory] = useState<Memory[] | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [action, setAction] = useState<"delete" | "restore" | null>(null);
  const canCreate = ["member", "family_admin"].includes(user.role);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setItems([]);
    api<Memory[]>(
      `/memories?deleted=${trash}&q=${encodeURIComponent(search)}&offset=${offset}&limit=50&sort=${timeline ? "event" : "updated"}&kind=${documents ? "document" : "all"}`,
      { signal: controller.signal },
    )
      .then(setItems)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [trash, search, offset, reload, timeline, documents]);
  const headers = {
    "Content-Type": "application/json",
    "X-CSRF-Token": user.csrf_token,
  };
  async function save(body: object) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await api<Memory>(
        selected ? `/memories/${selected.id}` : "/memories",
        {
          method: selected ? "PUT" : "POST",
          headers,
          body: JSON.stringify(body),
        },
      );
      setSelected(saved);
      setEditing(false);
      setHistory(null);
      setNotice("saved");
      setReload((value) => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function changeDeleted() {
    if (!selected || !action) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/memories/${selected.id}/${action}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          expected_revision: selected.revision,
          confirmed: true,
        }),
      });
      setNotice(action === "delete" ? "deleted" : "restored");
      setAction(null);
      setSelected(null);
      setHistory(null);
      setReload((value) => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function showHistory(nextOffset = 0) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      setHistory(
        await api<Memory[]>(
          `/memories/${selected.id}/history?offset=${nextOffset}`,
        ),
      );
      setHistoryOffset(nextOffset);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function back() {
    setSelected(null);
    setEditing(false);
    setHistory(null);
    setAction(null);
    setError("");
    setNotice("");
  }
  async function downloadMemory() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/memories/${selected.id}/export`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(t.exportError);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `claire-memory-${selected.id}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError(t.exportError);
    } finally {
      setBusy(false);
    }
  }
  const displayed = items;
  return (
    <section className="memory-panel">
      {error && <p role="alert">{error}</p>}
      {notice && (
        <p role="status" className="saved-notice">
          {t[notice]}
        </p>
      )}
      {editing ? (
        <Editor
          memory={selected}
          t={t}
          busy={busy}
          onSave={save}
          onCancel={() => {
            setEditing(false);
            setError("");
          }}
        />
      ) : selected ? (
        <>
          <button onClick={back}>{t.back}</button>
          <Story memory={selected} t={t} lang={lang} />
          {selected.owner_id === user.id && (
            <div>
              <button disabled={busy} onClick={downloadMemory}>
                {t.export}
              </button>
              <p>{t.exportNote}</p>
            </div>
          )}
          {selected.can_edit ? (
            <div className="memory-actions">
              {!selected.deleted && (
                <button
                  onClick={() => {
                    setEditing(true);
                    setHistory(null);
                    setNotice("");
                  }}
                >
                  {t.edit}
                </button>
              )}
              <button disabled={busy} onClick={() => showHistory()}>
                {t.history}
              </button>
              <button
                onClick={() =>
                  setAction(selected.deleted ? "restore" : "delete")
                }
              >
                {selected.deleted ? t.restore : t.remove}
              </button>
            </div>
          ) : (
            <p>{t.readOnly}</p>
          )}
          {action && (
            <div
              className="confirm-action"
              role="region"
              aria-label={t.approve}
            >
              <p>
                {action === "delete" ? t.deleteQuestion : t.restoreQuestion}
              </p>
              <button
                className="primary"
                disabled={busy}
                onClick={changeDeleted}
              >
                {t.approve}
              </button>
              <button disabled={busy} onClick={() => setAction(null)}>
                {t.cancel}
              </button>
            </div>
          )}
          {history && (
            <section className="history">
              <h2>{t.history}</h2>
              <p>{t.historyPrivate}</p>
              {history.map((memory) => (
                <details key={memory.revision}>
                  <summary>
                    {t.revision} {memory.revision} —{" "}
                    {new Date(memory.recorded_at).toLocaleString(lang)}
                    {memory.deleted ? ` · ${t.trash}` : ""}
                  </summary>
                  <Story memory={memory} t={t} lang={lang} />
                </details>
              ))}
              <div className="memory-actions">
                {historyOffset > 0 && (
                  <button
                    onClick={() => showHistory(Math.max(0, historyOffset - 50))}
                  >
                    {t.previous}
                  </button>
                )}
                {history.length === 50 && (
                  <button onClick={() => showHistory(historyOffset + 50)}>
                    {t.older}
                  </button>
                )}
              </div>
            </section>
          )}
        </>
      ) : (
        <>
          <div className="memory-toolbar">
            <div className="memory-tabs">
              <button
                aria-pressed={!trash}
                onClick={() => {
                  setTrash(false);
                  setOffset(0);
                }}
              >
                {t.active}
              </button>
              <button
                aria-pressed={trash}
                onClick={() => {
                  setTrash(true);
                  setOffset(0);
                }}
              >
                {t.trash}
              </button>
            </div>
            {canCreate && !documents && (
              <button
                className="primary"
                onClick={() => {
                  setEditing(true);
                  setSelected(null);
                  setNotice("");
                }}
              >
                {t.new}
              </button>
            )}
          </div>
          {canCreate && documents && (
            <ImportDocument
              user={user}
              lang={lang}
              onImported={(memory) => {
                setSelected(memory);
                setNotice("saved");
                setReload((value) => value + 1);
              }}
            />
          )}
          {canCreate && (
            <ImportMemory
              user={user}
              lang={lang}
              onImported={async (id) => {
                setSelected(await api<Memory>(`/memories/${id}`));
                setHistory(null);
                setAction(null);
                setNotice("saved");
                setReload((value) => value + 1);
              }}
            />
          )}
          <form
            className="memory-search"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(query);
              setOffset(0);
            }}
          >
            <input
              aria-label={t.search}
              placeholder={t.search}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              maxLength={200}
            />
            <button>{t.search}</button>
          </form>
          {loading ? (
            <p role="status">{t.loading}</p>
          ) : displayed.length ? (
            <div className="memory-list">
              {displayed.map((memory) => (
                <button
                  className="memory-row"
                  key={memory.id}
                  onClick={() => {
                    setSelected(memory);
                    setNotice("");
                  }}
                >
                  <span className="memory-row-title">{memory.title}</span>
                  <span>
                    {timeline
                      ? memory.event_date || t.noDate
                      : t[memory.verification]}
                  </span>
                  <small>
                    {memory.visibility === "private" ? t.private : t.family} ·{" "}
                    {t.revision} {memory.revision}
                  </small>
                </button>
              ))}
            </div>
          ) : (
            !error && (
              <div className="empty">
                <h2>
                  {!trash && !search && offset === 0
                    ? documents
                      ? lang === "fr"
                        ? "Votre bibliothèque de documents"
                        : "Your document library"
                      : t.empty
                    : t.noResults}
                </h2>
                {!trash && !search && (
                  <p>
                    {documents
                      ? lang === "fr"
                        ? "Importez un texte ou un fichier Markdown pour le conserver et le consulter avec CLAIRE."
                        : "Import text or Markdown to preserve it and consult it with CLAIRE."
                      : t.intro}
                  </p>
                )}
              </div>
            )
          )}
          <div className="memory-actions">
            {offset > 0 && (
              <button
                onClick={() => setOffset((value) => Math.max(0, value - 50))}
              >
                {t.previous}
              </button>
            )}
            {items.length === 50 && (
              <button onClick={() => setOffset((value) => value + 50)}>
                {t.next}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
