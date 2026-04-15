import Link from "next/link";

import { loginAction } from "@/app/login/actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const resolvedParams = (await searchParams) ?? {};
  const hasError = resolvedParams.error === "invalid";

  return (
    <div className="auth-shell">
      <div className="panel auth-card">
        <div className="section-header">
          <div>
            <h2>Grego Club Dashboard</h2>
            <p>Вход только для администратора. Данные берутся из общей Postgres-аналитики.</p>
          </div>
        </div>
        <form action={loginAction} className="auth-form">
          <label>
            <span className="muted">Пароль администратора</span>
            <input className="input" name="password" type="password" required />
          </label>
          {hasError ? <div className="badge">Неверный пароль</div> : null}
          <button type="submit">Войти</button>
        </form>
        <p className="page-subtitle">
          После авторизации будут доступны overview, funnel, stuck users и user journey.
          Вернуться к коду: <Link href="https://github.com/Marselvanlove/gregoclub">GitHub</Link>.
        </p>
      </div>
    </div>
  );
}
