import { useEffect, useState } from "react";
import {
  MessageCircle,
  BookOpen,
  Network,
  FileText,
  Image,
  Users,
  Puzzle,
  Cpu,
  CircleCheck,
  Settings,
  Lock,
} from "lucide-react";
import { api, type Identity, type Member } from "./api";
import { Login } from "./Login";
import { translations } from "./i18n";
import { Memories } from "./Memories";
import { Chat } from "./Chat";
import { Files } from "./Files";
import { Documents } from "./Documents";
import { ImmichSettings } from "./ImmichSettings";
const icons = [
  MessageCircle,
  BookOpen,
  Network,
  FileText,
  Image,
  Users,
  Puzzle,
  Cpu,
  CircleCheck,
  Settings,
];
const availableSections = new Set([0, 1, 2, 3, 4, 5]);

export default function App() {
  const [lang, setLang] = useState<"en" | "fr">("en");
  const [dark, setDark] = useState(false);
  const [user, setUser] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState("");
  const t = translations[lang];
  async function loadUser() {
    setUser(await api<Identity>("/auth/me"));
  }
  useEffect(() => {
    loadUser()
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
  }, [lang, dark]);
  useEffect(() => {
    if (!user || page !== 5) return;
    const controller = new AbortController();
    api<Member[]>("/family/members", { signal: controller.signal })
      .then(setMembers)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [user, page]);
  async function logout() {
    try {
      await api("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": user!.csrf_token },
      });
      setUser(null);
      setMembers([]);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const controls = (
    <div className="controls">
      <select
        aria-label="Language"
        value={lang}
        onChange={(e) => setLang(e.target.value as "en" | "fr")}
      >
        <option value="en">English</option>
        <option value="fr">Français</option>
      </select>
      <button onClick={() => setDark(!dark)}>{dark ? t.dark : t.light}</button>
    </div>
  );
  if (loading) return <p role="status">{t.loading}</p>;
  if (!user)
    return (
      <>
        {controls}
        <Login t={t} onLogin={loadUser} />
      </>
    );
  return (
    <div className="shell">
      <aside>
        <div className="brand">CLAIRE</div>
        <p className="subtitle">{t.subtitle}</p>
        <nav aria-label="Main">
          {t.nav.map((label, i) => {
            const Icon = icons[i];
            const available =
              availableSections.has(i) ||
              (i === 6 && user.role === "family_admin");
            return (
              <button
                key={i}
                disabled={!available}
                title={available ? undefined : t.pending}
                aria-current={page === i ? "page" : undefined}
                onClick={() => {
                  setPage(i);
                  setError("");
                }}
              >
                <Icon size={21} />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>
        <div className="account">
          <strong>{user.family.name}</strong>
          <small>{user.email}</small>
          <button onClick={logout}>{t.logout}</button>
        </div>
      </aside>
      <div className="workspace">
        <header>{controls}</header>
        <main className="content">
          <div className="title">
            <h1>{t.nav[page]}</h1>
          </div>
          {error && <p role="alert">{error}</p>}
          {page === 0 ? (
            <Chat key={user.id} user={user} lang={lang} />
          ) : page === 6 && user.role === "family_admin" ? (
            <ImmichSettings key={user.id} user={user} lang={lang} />
          ) : page === 4 ? (
            <Files key={user.id} user={user} lang={lang} />
          ) : page === 3 ? (
            <Documents key={user.id} user={user} lang={lang} />
          ) : page === 1 || page === 2 ? (
            <Memories
              key={`${user.id}-${page}`}
              user={user}
              lang={lang}
              timeline={page === 2}
            />
          ) : page === 5 ? (
            <div className="members">
              {members.map((m) => (
                <article key={m.id}>
                  <Users size={24} />
                  <div>
                    <strong>{m.email}</strong>
                    <p>{m.role}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <section className="empty">
              <h2>{page === 1 ? t.heading : t.nav[page]}</h2>
              {page === 1 && <p>{t.description}</p>}
              <p className="status">{t.pending}</p>
            </section>
          )}
          <footer>
            <Lock size={23} />
            <strong>{t.privacy}</strong>
          </footer>
        </main>
      </div>
    </div>
  );
}
