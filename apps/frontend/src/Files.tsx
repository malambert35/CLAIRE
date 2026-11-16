import { useEffect, useState, type FormEvent } from "react";
import { api, type Identity } from "./api";
import "./files.css";

type Asset = {
  id: string;
  owner_id: string;
  title: string;
  filename: string;
  description: string;
  category: string;
  mime: string;
  size: number;
  sha256: string;
  visibility: "private" | "family";
  deleted: boolean;
  revision: number;
};

export function Files({
  user,
  lang,
  documents = false,
}: {
  user: Identity;
  lang: "en" | "fr";
  documents?: boolean;
}) {
  const fr = lang === "fr";
  const [items, setItems] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState("private");
  const [confirmed, setConfirmed] = useState(false);
  const [open, setOpen] = useState(false);
  const [trash, setTrash] = useState(false);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<"" | "saved" | "changed">("");
  const [action, setAction] = useState<
    "share" | "private" | "delete" | "restore" | null
  >(null);
  const writable = ["member", "family_admin"].includes(user.role);
  const formats = documents ? "PDF" : "JPEG, PNG, WebP, MP3, WAV, MP4";
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    api<Asset[]>(
      `/assets?kind=${documents ? "document" : "media"}&deleted=${trash}&q=${encodeURIComponent(search)}&offset=${offset}`,
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
  }, [documents, trash, search, offset, reload]);
  function choose(next?: File) {
    setConfirmed(false);
    setError("");
    setFile(null);
    if (!next) return;
    const allowed = documents ? /\.pdf$/i : /\.(jpe?g|png|webp|mp3|wav|mp4)$/i;
    if (
      !allowed.test(next.name) ||
      next.size > 25 * 1024 * 1024 ||
      next.size === 0 ||
      next.name.length > 200
    ) {
      setError(
        fr
          ? `Formats : ${formats}. Maximum 25 Mio, fichier non vide.`
          : `Formats: ${formats}. Up to 25 MiB, non-empty file.`,
      );
      return;
    }
    setFile(next);
    setTitle(next.name.replace(/\.[^.]+$/, ""));
  }
  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || !confirmed) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<Asset>("/assets", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-CSRF-Token": user.csrf_token,
          "X-File-Metadata": encodeURIComponent(
            JSON.stringify({
              filename: file.name,
              title,
              description,
              visibility,
              confirmed,
            }),
          ),
        },
        body: file,
      });
      setSelected(result);
      setOpen(false);
      setFile(null);
      setConfirmed(false);
      setDescription("");
      setVisibility("private");
      setReload((r) => r + 1);
      setNotice("saved");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function change() {
    if (!selected || !action) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<Asset>(`/assets/${selected.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": user.csrf_token,
        },
        body: JSON.stringify({
          expected_revision: selected.revision,
          confirmed: true,
          ...(action === "share" || action === "private"
            ? { visibility: action === "share" ? "family" : "private" }
            : { deleted: action === "delete" }),
        }),
      });
      setSelected(result);
      setAction(null);
      setReload((r) => r + 1);
      setNotice("changed");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="file-library"
      aria-label={
        documents
          ? fr
            ? "Fichiers PDF"
            : "PDF files"
          : fr
            ? "Bibliothèque multimédia"
            : "Media library"
      }
    >
      {documents && (
        <h2>{fr ? "Fichiers PDF originaux" : "Original PDF files"}</h2>
      )}
      <p>
        {fr
          ? `Formats : ${formats} · 25 Mio maximum par fichier.`
          : `Formats: ${formats} · Up to 25 MiB per file.`}
      </p>
      <p>
        {fr
          ? "Les originaux sont conservés avec leurs métadonnées éventuelles (date, localisation…). Aucun OCR, transcription ou analyse IA automatique."
          : "Originals retain any embedded metadata (date, location…). No automatic OCR, transcription or AI analysis."}
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && (
        <p role="status" className="saved-notice">
          {notice === "saved"
            ? fr
              ? "Fichier enregistré."
              : "File saved."
            : fr
              ? "Modification enregistrée."
              : "Change saved."}
        </p>
      )}
      {selected ? (
        <article>
          <button
            onClick={() => {
              setSelected(null);
              setAction(null);
              setNotice("");
            }}
          >
            {fr ? "Retour aux fichiers" : "Back to files"}
          </button>
          <h2>{selected.title}</h2>
          <p>
            {selected.visibility === "private"
              ? fr
                ? "Moi uniquement"
                : "Only me"
              : fr
                ? "Ma famille"
                : "My family"}
            {selected.deleted && (fr ? " · Corbeille" : " · Deleted")}
          </p>
          {selected.category === "image" && (
            <img
              className="file-preview"
              src={`/api/v1/assets/${selected.id}/content`}
              alt={selected.title}
            />
          )}
          {selected.category === "audio" && (
            <audio
              className="file-preview"
              controls
              preload="metadata"
              src={`/api/v1/assets/${selected.id}/content`}
            />
          )}
          {selected.category === "video" && (
            <video
              className="file-preview"
              controls
              preload="metadata"
              src={`/api/v1/assets/${selected.id}/content`}
            />
          )}
          <p>{selected.description}</p>
          <p>
            {selected.filename} · {(selected.size / 1024).toFixed(1)}{" "}
            {fr ? "Kio" : "KiB"}
          </p>
          <p className="file-digest">SHA-256 : {selected.sha256}</p>
          <div className="file-actions">
            <a href={`/api/v1/assets/${selected.id}/content?download=true`}>
              {fr ? "Télécharger l’original" : "Download original"}
            </a>
            <a href={`/api/v1/assets/${selected.id}/export`}>
              {fr
                ? "Exporter avec les métadonnées (.zip)"
                : "Export with metadata (.zip)"}
            </a>
          </div>
          {selected.owner_id === user.id && writable && (
            <div className="file-actions">
              {!selected.deleted && (
                <button
                  disabled={busy}
                  onClick={() =>
                    setAction(
                      selected.visibility === "private" ? "share" : "private",
                    )
                  }
                >
                  {selected.visibility === "private"
                    ? fr
                      ? "Partager avec ma famille"
                      : "Share with family"
                    : fr
                      ? "Rendre privé"
                      : "Make private"}
                </button>
              )}
              <button
                disabled={busy}
                onClick={() =>
                  setAction(selected.deleted ? "restore" : "delete")
                }
              >
                {selected.deleted
                  ? fr
                    ? "Restaurer le fichier"
                    : "Restore file"
                  : fr
                    ? "Mettre à la corbeille"
                    : "Move file to trash"}
              </button>
            </div>
          )}
          {action && (
            <div className="confirm-action">
              <p>
                {action === "share"
                  ? fr
                    ? "Tous les membres de votre famille pourront consulter et télécharger cet original, y compris ses métadonnées."
                    : "All family members will be able to view and download this original, including its metadata."
                  : fr
                    ? "Confirmer cette modification ? Les copies déjà téléchargées ne peuvent pas être révoquées."
                    : "Confirm this change? Previously downloaded copies cannot be revoked."}
              </p>
              <button disabled={busy} onClick={change}>
                {fr ? "Confirmer" : "Confirm file change"}
              </button>
              <button disabled={busy} onClick={() => setAction(null)}>
                {fr ? "Annuler" : "Cancel"}
              </button>
            </div>
          )}
        </article>
      ) : (
        <>
          <div className="file-actions">
            <button
              aria-pressed={!trash}
              onClick={() => {
                setTrash(false);
                setOffset(0);
              }}
            >
              {fr ? "Fichiers actifs" : "Active files"}
            </button>
            <button
              aria-pressed={trash}
              onClick={() => {
                setTrash(true);
                setOffset(0);
              }}
            >
              {fr ? "Fichiers supprimés" : "Deleted files"}
            </button>
            {writable && (
              <button
                onClick={() => {
                  setOpen(!open);
                  setConfirmed(false);
                }}
              >
                {fr ? "Importer un fichier" : "Import file"}
              </button>
            )}
          </div>
          {open && (
            <form
              className="file-upload"
              onSubmit={upload}
              onChange={(e) => {
                if (!(
                  e.target instanceof HTMLInputElement &&
                  e.target.name === "file-confirm"
                ))
                  setConfirmed(false);
              }}
            >
              <label>
                {fr ? "Fichier original" : "Original file"}
                <input
                  type="file"
                  disabled={busy}
                  accept={
                    documents ? ".pdf" : ".jpg,.jpeg,.png,.webp,.mp3,.wav,.mp4"
                  }
                  onChange={(e) => choose(e.target.files?.[0])}
                />
              </label>
              {file && (
                <>
                  <p>
                    {file.name} · {(file.size / 1024).toFixed(1)}{" "}
                    {fr ? "Kio" : "KiB"}
                  </p>
                  <label>
                    {fr ? "Titre du fichier" : "File title"}
                    <input
                      required
                      maxLength={200}
                      disabled={busy}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </label>
                  <label>
                    {fr ? "Description" : "Description"}
                    <textarea
                      maxLength={2000}
                      disabled={busy}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                    />
                  </label>
                  <label>
                    {fr ? "Visibilité du fichier" : "File visibility"}
                    <select
                      disabled={busy}
                      value={visibility}
                      onChange={(e) => setVisibility(e.target.value)}
                    >
                      <option value="private">
                        {fr ? "Moi uniquement" : "Only me"}
                      </option>
                      <option value="family">
                        {fr ? "Ma famille" : "My family"}
                      </option>
                    </select>
                  </label>
                  <label>
                    <input
                      name="file-confirm"
                      type="checkbox"
                      disabled={busy}
                      checked={confirmed}
                      onChange={(e) => setConfirmed(e.target.checked)}
                    />
                    {fr
                      ? "Je confirme ce fichier et sa visibilité."
                      : "I confirm this file and its visibility."}
                  </label>
                  <button
                    disabled={busy || !confirmed || !title.trim()}
                    type="submit"
                  >
                    {busy
                      ? fr
                        ? "Enregistrement…"
                        : "Saving…"
                      : fr
                        ? "Enregistrer le fichier"
                        : "Save file"}
                  </button>
                </>
              )}
            </form>
          )}
          <form
            className="file-actions"
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(query);
              setOffset(0);
            }}
          >
            <input
              aria-label={fr ? "Rechercher des fichiers" : "Search files"}
              value={query}
              maxLength={200}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button>{fr ? "Rechercher des fichiers" : "Search files"}</button>
          </form>
          {loading ? (
            <p role="status">{fr ? "Chargement…" : "Loading…"}</p>
          ) : (
            <>
              {!items.length && (
                <p>
                  {fr
                    ? "Aucun fichier dans cette vue."
                    : "No files in this view."}
                </p>
              )}
              <div className="file-grid">
                {items.map((item) => (
                  <button
                    className="file-card"
                    key={item.id}
                    onClick={() => {
                      setSelected(item);
                      setNotice("");
                    }}
                  >
                    {item.category === "image" && (
                      <img
                        loading="lazy"
                        src={`/api/v1/assets/${item.id}/content`}
                        alt=""
                      />
                    )}
                    <strong>{item.title}</strong>
                    <span>
                      {item.category.toUpperCase()} ·{" "}
                      {(item.size / 1024).toFixed(1)} KiB
                    </span>
                    <span>
                      {item.visibility === "private"
                        ? fr
                          ? "Moi uniquement"
                          : "Only me"
                        : fr
                          ? "Ma famille"
                          : "My family"}
                    </span>
                  </button>
                ))}
              </div>
              <div className="file-actions">
                {offset > 0 && (
                  <button onClick={() => setOffset(Math.max(0, offset - 50))}>
                    {fr ? "Précédent" : "Previous"}
                  </button>
                )}
                {items.length === 50 && (
                  <button onClick={() => setOffset(offset + 50)}>
                    {fr ? "Suivant" : "Next"}
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
