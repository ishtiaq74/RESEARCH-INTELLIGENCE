"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiClientError,
  DocumentRead,
  getMe,
  listDocuments,
  logout,
  UserResponse,
} from "@/lib/api";
import styles from "./project-detail.module.css";

type PagePhase = "loading" | "not-found" | "error" | "ready";

function formatSizeMb(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function parseProjectId(raw: string | string[] | undefined): number | null {
  if (typeof raw !== "string" || !/^\d+$/.test(raw)) {
    return null;
  }
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    return null;
  }
  return parsed;
}

export default function ProjectDetailPage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  // Keep router in a ref so auth-error handling stays referentially stable and
  // never re-triggers the data-loading effect across renders or sign-out.
  const routerRef = useRef(router);
  useEffect(() => {
    routerRef.current = router;
  }, [router]);

  const projectId = parseProjectId(params.projectId);

  const [phase, setPhase] = useState<PagePhase>("loading");
  const [loadedForId, setLoadedForId] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentRead[]>([]);
  const [isSigningOut, setIsSigningOut] = useState(false);

  // Derive effective phase so invalid route params or a projectId change never
  // requires synchronous setState inside useEffect or flashes previous project data.
  const effectivePhase: PagePhase =
    projectId === null
      ? "not-found"
      : loadedForId !== projectId
        ? "loading"
        : phase;

  const clearPageState = useCallback(() => {
    setIsSigningOut(false);
    setUser(null);
    setDocuments([]);
    setLoadError(null);
    setLoadedForId(null);
    setPhase("loading");
  }, []);

  useEffect(() => {
    return () => {
      setIsSigningOut(false);
    };
  }, []);

  // Client-side auth redirect is for UX only; backend enforces ownership on every endpoint.
  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiClientError && err.status === 401) {
        clearPageState();
        routerRef.current.push("/login");
        return true;
      }
      return false;
    },
    [clearPageState]
  );

  const fetchProjectDocuments = useCallback(
    async (targetId: number) => {
      const [currentUser, docs] = await Promise.all([
        getMe(),
        listDocuments(targetId),
      ]);
      return { currentUser, docs };
    },
    []
  );

  useEffect(() => {
    if (projectId === null) {
      return;
    }

    const targetId = projectId;
    let active = true;

    async function loadInitialData() {
      try {
        const { currentUser, docs } = await fetchProjectDocuments(targetId);
        if (!active) return;
        setUser(currentUser);
        setDocuments(docs);
        setLoadError(null);
        setLoadedForId(targetId);
        setPhase("ready");
      } catch (err) {
        if (!active) return;
        if (handleAuthError(err)) return;
        setLoadedForId(targetId);
        if (err instanceof ApiClientError && err.status === 404) {
          setPhase("not-found");
          return;
        }
        setPhase("error");
        if (err instanceof ApiClientError) {
          setLoadError(err.message);
        } else {
          setLoadError("Could not load documents. Please try again.");
        }
      }
    }

    void loadInitialData();

    return () => {
      active = false;
    };
  }, [projectId, fetchProjectDocuments, handleAuthError]);

  async function handleRetry() {
    if (projectId === null) return;
    setLoadedForId(null);
    setPhase("loading");
    setLoadError(null);

    try {
      const { currentUser, docs } = await fetchProjectDocuments(projectId);
      setUser(currentUser);
      setDocuments(docs);
      setLoadedForId(projectId);
      setPhase("ready");
    } catch (err) {
      if (handleAuthError(err)) return;
      setLoadedForId(projectId);
      if (err instanceof ApiClientError && err.status === 404) {
        setPhase("not-found");
        return;
      }
      setPhase("error");
      if (err instanceof ApiClientError) {
        setLoadError(err.message);
      } else {
        setLoadError("Could not load documents. Please try again.");
      }
    }
  }

  async function handleSignOut() {
    setIsSigningOut(true);
    try {
      await logout();
    } catch {
      // Clear local UI state and redirect regardless of logout network errors.
    } finally {
      clearPageState();
      router.push("/login");
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <Link href="/projects" className={styles.backLink}>
              ← Back to Projects
            </Link>
            <h1 className={styles.brandHeading}>Project Documents</h1>
          </div>
          <div className={styles.userNav}>
            {user && (
              <span className={styles.userEmail}>
                Signed in as <strong>{user.email}</strong>
              </span>
            )}
            <button
              type="button"
              onClick={handleSignOut}
              disabled={isSigningOut}
              className={styles.signOutButton}
            >
              {isSigningOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>

        {effectivePhase === "loading" && (
          <div
            className={styles.loadingState}
            role="status"
            aria-live="polite"
          >
            <p>Loading project documents…</p>
          </div>
        )}

        {effectivePhase === "not-found" && (
          <div
            className={styles.errorBanner}
            role="alert"
            aria-live="polite"
          >
            <span>Project not found or you do not have access to it.</span>
            <Link href="/projects" className={styles.secondaryButton}>
              Back to Projects
            </Link>
          </div>
        )}

        {effectivePhase === "error" && (
          <div
            className={styles.errorBanner}
            role="alert"
            aria-live="polite"
          >
            <span>{loadError ?? "An error occurred."}</span>
            <button
              type="button"
              onClick={() => void handleRetry()}
              className={styles.secondaryButton}
            >
              Retry
            </button>
          </div>
        )}

        {effectivePhase === "ready" && (
          <section aria-labelledby="documents-heading">
            <h2 id="documents-heading" className={styles.sectionHeading}>
              Documents ({documents.length})
            </h2>

            {documents.length === 0 ? (
              <div className={styles.emptyState}>
                <p className={styles.emptyHeading}>No documents yet</p>
                <p className={styles.emptySubtitle}>
                  This project does not have any uploaded PDFs yet.
                </p>
              </div>
            ) : (
              <div className={styles.tableWrapper}>
                <table className={styles.documentTable}>
                  <thead>
                    <tr>
                      <th scope="col">Filename</th>
                      <th scope="col">Size</th>
                      <th scope="col">Pages</th>
                      <th scope="col">Status</th>
                      <th scope="col">Uploaded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr key={doc.id}>
                        {/* Plain JSX text interpolation only — never innerHTML or download links */}
                        <td className={styles.filenameCell}>
                          {doc.original_filename}
                        </td>
                        <td>{formatSizeMb(doc.size_bytes)}</td>
                        <td>{doc.page_count !== null ? doc.page_count : "-"}</td>
                        <td>{doc.status}</td>
                        <td>{new Date(doc.created_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
