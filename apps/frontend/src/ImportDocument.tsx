import { useState } from "react";
import { api, type Identity } from "./api";
import type { Memory } from "./Memories";

export function ImportDocument({
  user,
  lang,
  onImported,
}: {
  user: Identity;
  lang: "en" | "fr";
  onImported: (memory: Memory) => void;
}) {
  const fr = lang === "fr";
  const [open, setOpen] = useState(false);
  const [filename, setFilename] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [visibility, setVisibility] = useState("private");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const limits = fr
    ? "Fichier UTF-8 .txt ou .md, 8 Kio et 6 000 caractères maximum. PDF, Word et OCR ne sont pas encore pris en charge."
    : "UTF-8 .txt or .md file, up to 8 KiB and 6,000 characters. PDF, Word and OCR are not supported yet.";
  async function choose(file?: File) {
    setContent("");
    setFilename("");
    setConfirmed(false);
    setError("");
    if (!file) return;
    setBusy(true);
    try {
      if (
        file.size > 8192 ||
        file.name.length > 200 ||
        !/\.(txt|md|markdown)$/i.test(file.name)
      )
        throw new Error(limits);
      const text = new TextDecoder("utf-8", {
        fatal: true,
        ignoreBOM: true,
      }).decode(await file.arrayBuffer());
      if (
        !text.trim() ||
        [...text].length > 6000 ||
        /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(text)
      )
        throw new Error(limits);
      setFilename(file.name);
      setTitle(file.name.replace(/\.[^.]+$/, ""));
      setContent(text);
    } catch {
      setError(limits);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const memory = await api<Memory>("/memories/documents", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": user.csrf_token,
        },
        body: JSON.stringify({
          filename,
          title,
          content,
          visibility,
          confirmed,
          verification: "uncertain",
        }),
      });
      onImported(memory);
      setOpen(false);
      setContent("");
      setConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="document-import">
      <button disabled={busy} onClick={() => setOpen(!open)}>
        {fr ? "Importer un document" : "Import document"}
      </button>
      {open && (
        <div className="confirm-action">
          <p>{limits}</p>
          <label>
            {fr ? "Fichier texte ou Markdown" : "Text or Markdown file"}
            <input
              type="file"
              accept=".txt,.md,.markdown"
              disabled={busy}
              onChange={(e) => choose(e.target.files?.[0])}
            />
          </label>
          {content && (
            <>
              <label>
                {fr ? "Titre du document" : "Document title"}
                <input
                  value={title}
                  maxLength={200}
                  disabled={busy}
                  onChange={(e) => {
                    setTitle(e.target.value);
                    setConfirmed(false);
                  }}
                />
              </label>
              <label>
                {fr ? "Visibilité du document" : "Document visibility"}
                <select
                  value={visibility}
                  disabled={busy}
                  onChange={(e) => {
                    setVisibility(e.target.value);
                    setConfirmed(false);
                  }}
                >
                  <option value="private">
                    {fr ? "Moi uniquement" : "Only me"}
                  </option>
                  <option value="family">
                    {fr ? "Ma famille" : "My family"}
                  </option>
                </select>
              </label>
              <h3>
                {fr ? "Aperçu du texte original" : "Original text preview"}
              </h3>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  maxHeight: 320,
                  overflow: "auto",
                }}
              >
                {content}
              </pre>
              <p>
                {fr
                  ? "L’import ne vérifie pas les affirmations du document. Après confirmation, son texte pourra être consulté par votre Ollama local selon la visibilité choisie."
                  : "Import does not verify the document's claims. After confirmation, your local Ollama can use its text according to the chosen visibility."}
              </p>
              <label>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                {fr
                  ? "Je confirme ce document et sa visibilité."
                  : "I confirm this document and its visibility."}
              </label>
              <button
                disabled={busy || !confirmed || !title.trim()}
                onClick={save}
              >
                {fr ? "Enregistrer le document" : "Save document"}
              </button>
            </>
          )}
          {error && <p role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
