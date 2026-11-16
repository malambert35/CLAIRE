import { useState } from "react";
import type { Identity } from "./api";
import { Files } from "./Files";
import { Memories } from "./Memories";

export function Documents({
  user,
  lang,
}: {
  user: Identity;
  lang: "en" | "fr";
}) {
  const [pdf, setPdf] = useState(false);
  return (
    <>
      <div className="file-actions">
        <button aria-pressed={!pdf} onClick={() => setPdf(false)}>
          {lang === "fr" ? "Textes et Markdown" : "Text and Markdown"}
        </button>
        <button aria-pressed={pdf} onClick={() => setPdf(true)}>
          {lang === "fr" ? "Fichiers PDF" : "PDF originals"}
        </button>
      </div>
      {pdf ? (
        <Files user={user} lang={lang} documents />
      ) : (
        <Memories user={user} lang={lang} documents />
      )}
    </>
  );
}
