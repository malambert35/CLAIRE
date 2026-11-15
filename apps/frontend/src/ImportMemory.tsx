import { useState } from "react";
import { api, type Identity } from "./api";

type Preview = {
  sha256: string;
  title: string;
  revisions: number;
  content: string;
};

export function ImportMemory({
  user,
  lang,
  onImported,
}: {
  user: Identity;
  lang: "en" | "fr";
  onImported: (id: string) => Promise<void>;
}) {
  const fr = lang === "fr";
  const [opened, setOpened] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function upload(commit: boolean) {
    if (!file || (commit && (!preview || !confirmed))) return;
    setBusy(true);
    setError("");
    try {
      const headers: Record<string, string> = {
        "content-type": "application/zip",
        "x-csrf-token": user.csrf_token,
      };
      if (commit && preview) headers["x-import-confirm"] = preview.sha256;
      if (commit) {
        const result = await api<{ id: string }>("/memory-import/confirm", {
          method: "POST",
          headers,
          body: file,
        });
        setOpened(false);
        setFile(null);
        setPreview(null);
        setConfirmed(false);
        await onImported(result.id);
      } else {
        setPreview(
          await api<Preview>("/memory-import/preview", {
            method: "POST",
            headers,
            body: file,
          }),
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <button disabled={busy} onClick={() => setOpened(!opened)}>
        {fr ? "Importer un souvenir (.zip)" : "Import memory (.zip)"}
      </button>
      {opened && (
        <div className="confirm-action">
          <p>
            {fr
              ? "Importez uniquement un export CLAIRE que vous êtes autorisé à conserver. Une nouvelle copie privée sera créée avec son historique ; aucun souvenir existant ne sera remplacé. Les sommes de contrôle ne prouvent pas l’auteur du fichier."
              : "Import only a CLAIRE export you are allowed to keep. A new private copy with history will be created; existing memories are not replaced. Checksums do not prove authorship."}
          </p>
          <label>
            {fr ? "Fichier ZIP CLAIRE" : "CLAIRE ZIP file"}
            <input
              type="file"
              accept=".zip,application/zip"
              disabled={busy}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setPreview(null);
                setConfirmed(false);
                setError("");
              }}
            />
          </label>
          <button
            disabled={!file || busy || file.size > 34 * 1024 * 1024}
            onClick={() => upload(false)}
          >
            {fr ? "Vérifier et prévisualiser" : "Verify and preview"}
          </button>
          {file && file.size > 34 * 1024 * 1024 && (
            <p role="alert">{fr ? "Limite : 34 Mio." : "Limit: 34 MiB."}</p>
          )}
          {preview && (
            <div>
              <h3>{preview.title}</h3>
              <p>
                {preview.revisions}{" "}
                {fr ? "versions · copie privée" : "revisions · private copy"}
              </p>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {preview.content}
              </p>
              <label>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                {fr
                  ? "Je confirme la création de cette copie privée, y compris si le souvenir était supprimé."
                  : "I confirm creating this private copy, including if the memory was deleted."}
              </label>
              <button
                disabled={!confirmed || busy}
                onClick={() => upload(true)}
              >
                {fr ? "Créer la copie privée" : "Create private copy"}
              </button>
            </div>
          )}
          {error && <p role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
