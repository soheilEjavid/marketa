import { FormEvent, useState } from "react";
import { LogIn } from "lucide-react";

import { ApiError, login } from "../api";
import { useI18n } from "../i18n";
import { setSession, type Session } from "../session";

type LoginProps = {
  onLoginSuccess: (session: Session) => void;
};

export function Login({ onLoginSuccess }: LoginProps) {
  const { t, direction } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const result = await login(username, password);
      const session: Session = {
        token: result.token,
        userId: result.userId,
        username: result.username,
        fullName: result.fullName,
        role: result.role,
      };
      setSession(session);
      onLoginSuccess(session);
    } catch (err) {
      if (err instanceof ApiError) {
        // status is set for any real HTTP response (wrong credentials =
        // 401, inactive account = 403); its absence means fetch() itself
        // threw — a genuine connectivity failure, not a login problem.
        if (err.status === 403) {
          setError(t("accountInactive"));
        } else if (err.status !== undefined) {
          setError(t("loginFailed"));
        } else {
          setError(t("loginError"));
        }
      } else {
        setError(t("loginError"));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page" dir={direction}>
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-brand">
          <span className="brand-mark">M</span>
          <strong>{t("localStore")}</strong>
          <small>{t("brandSubtitle")}</small>
        </div>

        <h1>{t("loginTitle")}</h1>

        <div className="field">
          <label htmlFor="login-username">{t("username")}</label>
          <input
            id="login-username"
            type="text"
            placeholder={t("usernamePlaceholder")}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </div>

        <div className="field">
          <label htmlFor="login-password">{t("password")}</label>
          <input
            id="login-password"
            type="password"
            placeholder={t("passwordPlaceholder")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        {error && <div className="feedback-banner error">{error}</div>}

        <button
          type="submit"
          className={`primary-button login-submit ${loading ? "is-loading" : ""}`}
          disabled={loading}
        >
          <LogIn size={18} />
          {loading ? t("loading") : t("signIn")}
        </button>
      </form>
    </div>
  );
}
