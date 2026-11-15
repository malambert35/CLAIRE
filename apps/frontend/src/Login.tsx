import { useState, type FormEvent } from "react";
import { api } from "./api";
import { translations } from "./i18n";
export function Login({
  t,
  onLogin,
}: {
  t: typeof translations.en;
  onLogin: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
        }),
      });
      await onLogin();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <div className="brand">CLAIRE</div>
      <p>{t.subtitle}</p>
      <h1>{t.signIn}</h1>
      <p>{t.access}</p>
      <form onSubmit={submit}>
        <label>
          {t.email}
          <input
            name="email"
            type="email"
            autoComplete="username"
            required
            maxLength={254}
          />
        </label>
        <label>
          {t.password}
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={1024}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button className="primary" disabled={busy}>
          {busy ? t.loading : t.signIn}
        </button>
      </form>
      <small>{t.provision}</small>
    </main>
  );
}
