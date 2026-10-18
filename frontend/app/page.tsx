"use client";

import { useEffect, useState } from "react";
import styles from "./page.module.css";

interface HealthData {
  status: string;
  version: string;
  app_name: string;
}

type FetchState =
  | { phase: "loading" }
  | { phase: "ok"; data: HealthData }
  | { phase: "error"; message: string };

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [state, setState] = useState<FetchState>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function fetchHealth() {
      try {
        const res = await fetch(`${API_BASE_URL}/health`, {
          signal: controller.signal,
        });
        if (!res.ok) {
          setState({
            phase: "error",
            message: `Backend returned HTTP ${res.status} ${res.statusText}`,
          });
          return;
        }
        const data: HealthData = (await res.json()) as HealthData;
        setState({ phase: "ok", data });
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setState({
          phase: "error",
          message:
            "Could not reach the backend. Is it running on " +
            API_BASE_URL +
            "?",
        });
      }
    }

    void fetchHealth();
    return () => controller.abort();
  }, []);

  return (
    <main className={styles.main}>
      <h1 className={styles.heading}>Research Intelligence</h1>
      <p className={styles.subtitle}>Backend health status</p>

      <div className={styles.card} aria-live="polite" aria-atomic="true">
        {state.phase === "loading" && (
          <p className={styles.loading}>Checking backend…</p>
        )}

        {state.phase === "error" && (
          <div className={styles.error} role="alert">
            <span className={styles.errorIcon}>⚠</span>
            <p>{state.message}</p>
          </div>
        )}

        {state.phase === "ok" && (
          <dl className={styles.details}>
            <div className={styles.row}>
              <dt>Status</dt>
              <dd className={styles.statusOk}>{state.data.status}</dd>
            </div>
            <div className={styles.row}>
              <dt>App name</dt>
              <dd>{state.data.app_name}</dd>
            </div>
            <div className={styles.row}>
              <dt>Version</dt>
              <dd>{state.data.version}</dd>
            </div>
          </dl>
        )}
      </div>

      <p className={styles.hint}>
        Backend URL:{" "}
        <code className={styles.code}>{API_BASE_URL}/health</code>
      </p>
    </main>
  );
}
