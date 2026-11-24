"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  ApiClientError,
  deleteDocument,
  DocumentRead,
  documentUploadErrorMessage,
  getMe,
  listDocuments,
  logout,
  uploadDocument,
  UserResponse,
} from "@/lib/api";
import styles from "./project-detail.module.css";

// These mirror server limits and must change together (D-031).
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024; // 20 MiB
const ACCEPTED_EXTENSION = ".pdf";

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

function ProjectDetailContent() {
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
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
    setSelectedFile(null);
    setIsUploading(false);
    setUploadError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setDeletingId(null);
    setIsDeleting(false);
    setDeleteError(null);
    setLoadError(null);
    setLoadedForId(null);
    setPhase("loading");
  }, []);

  useEffect(() => {
    const inputEl = fileInputRef.current;
    return () => {
      // Next.js 16 cacheComponents preserves component state across navigations
      // via React <Activity>. Reset transient selection, confirmation, and error
      // state when leaving or switching projects so stale state never carries over.
      setIsSigningOut(false);
      setIsUploading(false);
      setIsDeleting(false);
      setSelectedFile(null);
      setUploadError(null);
      setDeletingId(null);
      setDeleteError(null);
      if (inputEl) {
        inputEl.value = "";
      }
    };
  }, [projectId]);

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
        setSelectedFile(null);
        setUploadError(null);
        setDeletingId(null);
        setDeleteError(null);
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

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setUploadError(null);
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
  }

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (projectId === null || !selectedFile) return;

    setUploadError(null);

    // Client-side pre-checks for fast UX feedback; the server enforces limits authoritatively.
    if (!selectedFile.name.toLowerCase().endsWith(ACCEPTED_EXTENSION)) {
      setUploadError("Not a PDF.");
      return;
    }
    if (selectedFile.size > MAX_UPLOAD_BYTES) {
      setUploadError("Larger than 20 MB.");
      return;
    }

    setIsUploading(true);
    try {
      await uploadDocument(projectId, selectedFile);
      const refreshed = await listDocuments(projectId);
      setDocuments(refreshed);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      if (err instanceof ApiClientError) {
        setUploadError(documentUploadErrorMessage(err));
      } else {
        setUploadError("Upload failed. Please try again.");
      }
    } finally {
      setIsUploading(false);
    }
  }

  function startDelete(documentId: number) {
    setDeletingId(documentId);
    setDeleteError(null);
  }

  function cancelDelete() {
    setDeletingId(null);
    setDeleteError(null);
  }

  async function handleConfirmDelete(documentId: number) {
    if (projectId === null) return;
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await deleteDocument(projectId, documentId);
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
      setDeletingId(null);
    } catch (err) {
      if (handleAuthError(err)) return;
      if (err instanceof ApiClientError) {
        setDeleteError(err.message);
      } else {
        setDeleteError("Failed to delete document. Please try again.");
      }
    } finally {
      setIsDeleting(false);
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
          <>
            <section className={styles.card} aria-labelledby="upload-heading">
              <h2 id="upload-heading" className={styles.sectionHeading}>
                Upload PDF
              </h2>
              <form onSubmit={handleUpload} className={styles.uploadForm}>
                <label htmlFor="pdf-upload" className={styles.label}>
                  Select PDF file
                </label>
                <div className={styles.uploadRow}>
                  <input
                    ref={fileInputRef}
                    id="pdf-upload"
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={handleFileChange}
                    disabled={isUploading}
                    className={styles.fileInput}
                  />
                  <button
                    type="submit"
                    disabled={!selectedFile || isUploading}
                    className={styles.primaryButton}
                  >
                    {isUploading ? "Uploading…" : "Upload"}
                  </button>
                </div>
                <div
                  aria-live="polite"
                  aria-atomic="true"
                  className={uploadError ? styles.formError : styles.hint}
                >
                  {uploadError ? (
                    <span role="alert">{uploadError}</span>
                  ) : (
                    <span>PDF only, maximum 20 MB.</span>
                  )}
                </div>
              </form>
            </section>

            <section aria-labelledby="documents-heading">
              <h2 id="documents-heading" className={styles.sectionHeading}>
                Documents ({documents.length})
              </h2>

              {deleteError && (
                <div
                  className={styles.formError}
                  role="alert"
                  aria-live="polite"
                  style={{ marginBottom: "0.75rem" }}
                >
                  {deleteError}
                </div>
              )}

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
                        <th scope="col">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((doc) => {
                        const isBeingDeleted = deletingId === doc.id;

                        return (
                          <tr key={doc.id}>
                            {/* Plain JSX text interpolation only — never innerHTML or download links */}
                            <td className={styles.filenameCell}>
                              {doc.original_filename}
                            </td>
                            <td>{formatSizeMb(doc.size_bytes)}</td>
                            <td>
                              {doc.page_count !== null ? doc.page_count : "-"}
                            </td>
                            <td>{doc.status}</td>
                            <td>
                              {new Date(doc.created_at).toLocaleDateString()}
                            </td>
                            <td>
                              {isBeingDeleted ? (
                                <div className={styles.deleteActions}>
                                  <span className={styles.deleteWarningText}>
                                    Delete this document?
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void handleConfirmDelete(doc.id)
                                    }
                                    disabled={isDeleting}
                                    className={styles.confirmDeleteButton}
                                  >
                                    {isDeleting ? "Deleting…" : "Confirm Delete"}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={cancelDelete}
                                    disabled={isDeleting}
                                    className={styles.secondaryButton}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => startDelete(doc.id)}
                                  className={styles.dangerButton}
                                >
                                  Delete
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

export default function ProjectDetailPage() {
  // Next.js 16 cacheComponents requires dynamic URL hooks like useParams() to be
  // inside a <Suspense> boundary so the static shell can prerender cleanly.
  return (
    <Suspense
      fallback={
        <div className={styles.page}>
          <div className={styles.container}>
            <div className={styles.loadingState} role="status" aria-live="polite">
              <p>Loading project documents…</p>
            </div>
          </div>
        </div>
      }
    >
      <ProjectDetailContent />
    </Suspense>
  );
}
