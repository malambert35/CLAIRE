import { useEffect, useState, type FormEvent } from "react";
import { api, type Identity } from "./api";
import "./files.css";

type Connection = {
  endpoint: string;
  enabled: boolean;
  has_token: boolean;
  revision: number;
};
type Result = {
  connected?: boolean;
  tools?: string[];
  items?: { id: string; title: string; type: string; date: string }[];
  limited?: boolean;
};
export function ImmichSettings({
  user,
  lang,
}: {
  user: Identity;
  lang: "en" | "fr";
}) {
  const fr = lang === "fr";
  const [config, setConfig] = useState<Connection | null>(null);
  const [endpoint, setEndpoint] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [token, setToken] = useState("");
  const [clearToken, setClearToken] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [query, setQuery] = useState("");
  const [remove, setRemove] = useState(false);
  const headers = {
    "Content-Type": "application/json",
    "X-CSRF-Token": user.csrf_token,
  };
  function load(value: Connection) {
    setConfig(value);
    setEndpoint(value.endpoint);
    setEnabled(value.enabled);
    setToken("");
    setClearToken(false);
    setConfirmed(false);
    setDirty(false);
    setResult(null);
  }
  useEffect(() => {
    const controller = new AbortController();
    api<Connection>("/integrations/immich", { signal: controller.signal })
      .then(load)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!config || !confirmed) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      load(
        await api<Connection>("/integrations/immich", {
          method: "PUT",
          headers,
          body: JSON.stringify({
            endpoint,
            enabled,
            token: clearToken ? "" : token || null,
            expected_revision: config.revision,
            confirmed,
          }),
        }),
      );
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function read(action: "test" | "recent" | "albums" | "search") {
    setBusy(true);
    setError("");
    setResult(null);
    setSaved(false);
    try {
      setResult(
        await api<Result>("/integrations/immich/read", {
          method: "POST",
          headers,
          body: JSON.stringify({ action, query }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function disconnect() {
    setBusy(true);
    setError("");
    try {
      await api("/integrations/immich", { method: "DELETE", headers });
      load({ endpoint: "", enabled: false, has_token: false, revision: 0 });
      setRemove(false);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Immich MCP">
      <h2>Immich MCP</h2>
      <p>
        {fr
          ? "Configuration réservée à l’administrateur. Cette connexion et ses résultats restent accessibles uniquement à l’administrateur qui la configure."
          : "Administrator configuration. Only the administrator who configures this connection can access it and its results."}
      </p>
      <p>
        {fr
          ? "barryw/ImmichMCP utilise la clé Immich définie dans son conteneur. Le connecter ici ne partage pas automatiquement ses photos avec la famille. Deux serveurs utilisant la même clé exposent la même bibliothèque."
          : "barryw/ImmichMCP uses the Immich key configured in its container. Connecting it here does not automatically share photos with your family. Servers using the same key expose the same library."}
      </p>
      {error && <p role="alert">{error}</p>}
      {saved && (
        <p role="status">
          {fr ? "Configuration enregistrée." : "Configuration saved."}
        </p>
      )}
      {!config ? (
        <p>
          {fr ? "Chargement de la configuration…" : "Loading configuration…"}
        </p>
      ) : (
        <>
          <form
            className="file-upload"
            onSubmit={save}
            onChange={(e) => {
              if (!(
                e.target instanceof HTMLInputElement &&
                e.target.name === "confirm-mcp"
              )) {
                setConfirmed(false);
                setDirty(true);
                setSaved(false);
                setResult(null);
              }
            }}
          >
            <label>
              {fr ? "Adresse du serveur MCP" : "MCP server address"}
              <input
                type="url"
                required
                maxLength={1000}
                disabled={busy}
                value={endpoint}
                placeholder="http://192.168.1.20:5000/mcp"
                onChange={(e) => setEndpoint(e.target.value)}
              />
            </label>
            <p>
              {fr
                ? "Transport : Streamable HTTP (/mcp). Utilisez l’adresse réseau accessible depuis le conteneur CLAIRE ; localhost ne désigne pas votre serveur Unraid."
                : "Transport: Streamable HTTP (/mcp). Use an address reachable from the CLAIRE container; localhost does not refer to your Unraid host."}
            </p>
            <label>
              {fr
                ? "Jeton Bearer du proxy MCP (facultatif)"
                : "MCP proxy Bearer token (optional)"}
              <input
                type="password"
                autoComplete="new-password"
                maxLength={4096}
                disabled={busy || clearToken}
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
            <p>
              {fr
                ? "Ce n’est pas la clé API Immich. Laissez vide si votre serveur MCP n’exige pas d’authentification. Un jeton déjà enregistré est conservé si vous laissez ce champ vide."
                : "This is not the Immich API key. Leave empty if your MCP server requires no authentication. An existing token is retained when this field is blank."}
            </p>
            {config.has_token && (
              <label>
                <input
                  type="checkbox"
                  checked={clearToken}
                  disabled={busy}
                  onChange={(e) => setClearToken(e.target.checked)}
                />
                {fr ? "Supprimer le jeton enregistré" : "Remove saved token"}
              </label>
            )}
            <label>
              <input
                type="checkbox"
                checked={enabled}
                disabled={busy}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              {fr ? "Activer la connexion Immich" : "Enable Immich connection"}
            </label>
            <label>
              <input
                name="confirm-mcp"
                type="checkbox"
                checked={confirmed}
                disabled={busy}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              {fr
                ? "Je confirme ce serveur et l’accès à la bibliothèque associée."
                : "I confirm this server and access to its library."}
            </label>
            <button type="submit" disabled={busy || !confirmed}>
              {fr ? "Enregistrer la connexion" : "Save connection"}
            </button>
          </form>
          {config.revision > 0 && (
            <>
              <div className="file-actions">
                <button disabled={busy || dirty} onClick={() => read("test")}>
                  {fr ? "Tester la connexion" : "Test connection"}
                </button>
                <button
                  disabled={busy || dirty || !config.enabled}
                  onClick={() => read("recent")}
                >
                  {fr ? "Médias récents" : "Recent media"}
                </button>
                <button
                  disabled={busy || dirty || !config.enabled}
                  onClick={() => read("albums")}
                >
                  {fr ? "Albums Immich" : "Immich albums"}
                </button>
                <button disabled={busy} onClick={() => setRemove(true)}>
                  {fr ? "Supprimer la connexion" : "Delete connection"}
                </button>
              </div>
              <form
                className="file-actions"
                onSubmit={(e) => {
                  e.preventDefault();
                  read("search");
                }}
              >
                <input
                  aria-label={fr ? "Nom de fichier Immich" : "Immich filename"}
                  maxLength={200}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button
                  disabled={busy || dirty || !config.enabled || !query.trim()}
                >
                  {fr ? "Rechercher dans Immich" : "Search Immich"}
                </button>
              </form>
              {dirty && (
                <p>
                  {fr
                    ? "Enregistrez vos modifications avant de tester ou consulter la connexion."
                    : "Save your changes before testing or browsing this connection."}
                </p>
              )}
            </>
          )}
          {remove && (
            <div className="confirm-action">
              <p>
                {fr
                  ? "Supprimer cette configuration et son jeton ? Les fichiers Immich ne seront pas modifiés."
                  : "Delete this configuration and its token? Immich files will not be changed."}
              </p>
              <button disabled={busy} onClick={disconnect}>
                {fr ? "Confirmer la suppression" : "Confirm deletion"}
              </button>
              <button disabled={busy} onClick={() => setRemove(false)}>
                {fr ? "Annuler" : "Cancel"}
              </button>
            </div>
          )}
          {busy && (
            <p role="status">{fr ? "Connexion en cours…" : "Connecting…"}</p>
          )}
          {result?.connected && (
            <div role="status">
              <strong>
                {fr
                  ? "Connexion Immich confirmée."
                  : "Immich connection confirmed."}
              </strong>
              <p>
                {fr
                  ? "Outils de lecture compatibles :"
                  : "Compatible read tools:"}
              </p>
              <ul>
                {result.tools?.map((tool) => (
                  <li key={tool}>{tool}</li>
                ))}
              </ul>
            </div>
          )}
          {result?.items && (
            <div>
              <h3>{fr ? "Résultats Immich" : "Immich results"}</h3>
              {!result.items.length && (
                <p>{fr ? "Aucun résultat." : "No results."}</p>
              )}
              <ul>
                {result.items.map((item, i) => (
                  <li key={`${item.id}-${i}`}>
                    <strong>{item.title || item.id}</strong>
                    <p>
                      {item.type} {item.date}
                    </p>
                  </li>
                ))}
              </ul>
              <p>
                {fr
                  ? "Liste limitée aux premiers résultats. Les originaux restent dans Immich ; aucune copie automatique, modification ni transmission au chat."
                  : "Limited to the first results. Originals stay in Immich; no automatic copying, editing or transmission to chat."}
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
