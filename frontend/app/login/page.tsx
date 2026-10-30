"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiClientError, getMe, login } from "@/lib/api";
import styles from "../auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Client-side guard is for UX only; the backend enforces access on all protected endpoints.
  useEffect(() => {
    let active = true;
    getMe()
      .then(() => {
        if (active) {
          router.push("/projects");
        }
      })
      .catch(() => {
        // User is not authenticated; remain on sign-in page
      });

    return () => {
      active = false;
    };
  }, [router]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    // Client-side hints (the backend server is authoritative)
    if (password.length < 8 || password.length > 128) {
      setError("Password must be between 8 and 128 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/projects");
    } catch (err) {
      if (err instanceof ApiClientError) {
        // Display server message as is (generic "Invalid email or password.")
        // Never reveals whether an email exists.
        setError(err.message);
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className={styles.container}>
      <h1 className={styles.heading}>Research Intelligence</h1>
      <p className={styles.subtitle}>Sign in to your research workspace</p>

      <div className={styles.card}>
        <form onSubmit={handleSubmit} className={styles.form} noValidate>
          <div
            aria-live="polite"
            aria-atomic="true"
            className={error ? styles.error : undefined}
            role={error ? "alert" : undefined}
          >
            {error && (
              <>
                <span className={styles.errorIcon} aria-hidden="true">
                  ⚠
                </span>
                <p>{error}</p>
              </>
            )}
          </div>

          <div className={styles.field}>
            <label htmlFor="login-email" className={styles.label}>
              Email address
            </label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className={styles.input}
              placeholder="researcher@university.edu"
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="login-password" className={styles.label}>
              Password
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className={styles.input}
              placeholder="••••••••"
            />
            <p className={styles.hint}>
              Password must be 8 to 128 characters.
            </p>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className={styles.button}
          >
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className={styles.footer}>
          Don&apos;t have an account? <Link href="/register">Sign up</Link>
        </p>
      </div>
    </main>
  );
}
