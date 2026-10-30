"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ApiClientError,
  createProject,
  deleteProject,
  getMe,
  listProjects,
  logout,
  ProjectResponse,
  renameProject,
  UserResponse,
} from "@/lib/api";
import styles from "./projects.module.css";

type PagePhase = "loading" | "error" | "ready";

export default function ProjectsPage() {
  const router = useRouter();

  const [phase, setPhase] = useState<PagePhase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [user, setUser] = useState<UserResponse | null>(null);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);

  // Create form state
  const [newProjectName, setNewProjectName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Inline rename state
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);

  // Delete confirmation state
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Sign out state
  const [isSigningOut, setIsSigningOut] = useState(false);

  // Note: This client-side guard is for UX only; the backend enforces access on all protected endpoints.
  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiClientError && err.status === 401) {
        router.push("/login");
        return true;
      }
      return false;
    },
    [router]
  );

  const reloadData = useCallback(async () => {
    setPhase("loading");
    setLoadError(null);

    try {
      const [currentUser, userProjects] = await Promise.all([
        getMe(),
        listProjects(),
      ]);
      setUser(currentUser);
      setProjects(userProjects);
      setPhase("ready");
    } catch (err) {
      if (handleAuthError(err)) return;
      setPhase("error");
      if (err instanceof ApiClientError) {
        setLoadError(err.message);
      } else {
        setLoadError("Could not load projects. Please try again.");
      }
    }
  }, [handleAuthError]);

  useEffect(() => {
    let active = true;

    async function loadInitialData() {
      try {
        const [currentUser, userProjects] = await Promise.all([
          getMe(),
          listProjects(),
        ]);
        if (!active) return;
        setUser(currentUser);
        setProjects(userProjects);
        setPhase("ready");
      } catch (err) {
        if (!active) return;
        if (handleAuthError(err)) return;
        setPhase("error");
        if (err instanceof ApiClientError) {
          setLoadError(err.message);
        } else {
          setLoadError("Could not load projects. Please try again.");
        }
      }
    }

    void loadInitialData();

    return () => {
      active = false;
    };
  }, [handleAuthError]);

  async function handleSignOut() {
    setIsSigningOut(true);
    try {
      await logout();
    } catch {
      // Regardless of network status, clear local UX and redirect to login
    } finally {
      router.push("/login");
    }
  }

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setCreateError(null);

    const trimmed = newProjectName.trim();
    if (!trimmed) {
      setCreateError("Project name cannot be empty.");
      return;
    }
    if (trimmed.length > 100) {
      setCreateError("Project name must not exceed 100 characters.");
      return;
    }

    setIsCreating(true);
    try {
      const created = await createProject(trimmed);
      setProjects((prev) => [...prev, created]);
      setNewProjectName("");
    } catch (err) {
      if (handleAuthError(err)) return;
      if (err instanceof ApiClientError) {
        setCreateError(err.message);
      } else {
        setCreateError("Failed to create project. Please try again.");
      }
    } finally {
      setIsCreating(false);
    }
  }

  function startRename(project: ProjectResponse) {
    setRenamingId(project.id);
    setRenameValue(project.name);
    setRenameError(null);
    setDeletingId(null);
  }

  function cancelRename() {
    setRenamingId(null);
    setRenameValue("");
    setRenameError(null);
  }

  async function handleSaveRename(projectId: number) {
    setRenameError(null);
    const trimmed = renameValue.trim();
    if (!trimmed) {
      setRenameError("Project name cannot be empty.");
      return;
    }
    if (trimmed.length > 100) {
      setRenameError("Project name must not exceed 100 characters.");
      return;
    }

    setIsRenaming(true);
    try {
      const updated = await renameProject(projectId, trimmed);
      setProjects((prev) =>
        prev.map((p) => (p.id === projectId ? updated : p))
      );
      setRenamingId(null);
      setRenameValue("");
    } catch (err) {
      if (handleAuthError(err)) return;
      if (err instanceof ApiClientError) {
        setRenameError(err.message);
      } else {
        setRenameError("Failed to rename project.");
      }
    } finally {
      setIsRenaming(false);
    }
  }

  function startDelete(projectId: number) {
    setDeletingId(projectId);
    setDeleteError(null);
    setRenamingId(null);
  }

  function cancelDelete() {
    setDeletingId(null);
    setDeleteError(null);
  }

  async function handleConfirmDelete(projectId: number) {
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
      setDeletingId(null);
    } catch (err) {
      if (handleAuthError(err)) return;
      if (err instanceof ApiClientError) {
        setDeleteError(err.message);
      } else {
        setDeleteError("Failed to delete project. Please try again.");
      }
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Navigation & User Header */}
        <header className={styles.header}>
          <h1 className={styles.brandHeading}>Research Intelligence</h1>
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

        {/* Global Error Banner */}
        {phase === "error" && (
          <div
            className={styles.errorBanner}
            role="alert"
            aria-live="polite"
          >
            <span>{loadError ?? "An error occurred."}</span>
            <button
              type="button"
              onClick={() => void reloadData()}
              className={styles.secondaryButton}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading State */}
        {phase === "loading" && (
          <div
            className={styles.loadingState}
            role="status"
            aria-live="polite"
          >
            <p>Loading your research projects…</p>
          </div>
        )}

        {/* Ready State */}
        {phase === "ready" && (
          <>
            {/* Create Project Card */}
            <section className={styles.card} aria-labelledby="create-heading">
              <h2 id="create-heading" className={styles.sectionHeading}>
                Create New Project
              </h2>
              <form onSubmit={handleCreate} className={styles.createForm}>
                <label htmlFor="new-project-name" className={styles.label}>
                  Project name
                </label>
                <div className={styles.createRow}>
                  <input
                    id="new-project-name"
                    type="text"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    placeholder="e.g. LLM Reasoning Papers"
                    className={styles.input}
                    disabled={isCreating}
                    maxLength={100}
                  />
                  <button
                    type="submit"
                    disabled={isCreating}
                    className={styles.primaryButton}
                  >
                    {isCreating ? "Creating…" : "Create Project"}
                  </button>
                </div>
                <div
                  aria-live="polite"
                  aria-atomic="true"
                  className={createError ? styles.formError : styles.hint}
                >
                  {createError ? (
                    <span role="alert">{createError}</span>
                  ) : (
                    <span>Name must be between 1 and 100 characters.</span>
                  )}
                </div>
              </form>
            </section>

            {/* Project List / Empty State */}
            <section aria-labelledby="projects-heading">
              <h2 id="projects-heading" className={styles.sectionHeading}>
                Your Projects ({projects.length})
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

              {projects.length === 0 ? (
                <div className={styles.emptyState}>
                  <p className={styles.emptyHeading}>No projects yet</p>
                  <p className={styles.emptySubtitle}>
                    Create your first research project above to start uploading
                    papers and querying literature.
                  </p>
                </div>
              ) : (
                <ul className={styles.projectList}>
                  {projects.map((project) => {
                    const isBeingRenamed = renamingId === project.id;
                    const isBeingDeleted = deletingId === project.id;

                    return (
                      <li key={project.id} className={styles.projectItem}>
                        {isBeingDeleted ? (
                          <div className={styles.deleteConfirmation}>
                            <span className={styles.deleteWarningText}>
                              Delete &ldquo;{project.name}&rdquo;? This cannot be undone.
                            </span>
                            <div className={styles.actions}>
                              <button
                                type="button"
                                onClick={() => handleConfirmDelete(project.id)}
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
                          </div>
                        ) : isBeingRenamed ? (
                          <div className={styles.inlineRenameForm}>
                            <input
                              type="text"
                              value={renameValue}
                              onChange={(e) => setRenameValue(e.target.value)}
                              className={styles.inlineRenameInput}
                              disabled={isRenaming}
                              maxLength={100}
                              aria-label={`Rename project ${project.name}`}
                            />
                            <button
                              type="button"
                              onClick={() => handleSaveRename(project.id)}
                              disabled={isRenaming}
                              className={styles.primaryButton}
                            >
                              {isRenaming ? "Saving…" : "Save"}
                            </button>
                            <button
                              type="button"
                              onClick={cancelRename}
                              disabled={isRenaming}
                              className={styles.secondaryButton}
                            >
                              Cancel
                            </button>
                            {renameError && (
                              <div
                                className={styles.formError}
                                role="alert"
                                aria-live="polite"
                              >
                                {renameError}
                              </div>
                            )}
                          </div>
                        ) : (
                          <>
                            <div className={styles.projectDetails}>
                              <span className={styles.projectName}>
                                {project.name}
                              </span>
                              <span className={styles.projectMeta}>
                                Created:{" "}
                                {new Date(project.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            <div className={styles.actions}>
                              <button
                                type="button"
                                onClick={() => startRename(project)}
                                className={styles.secondaryButton}
                              >
                                Rename
                              </button>
                              <button
                                type="button"
                                onClick={() => startDelete(project.id)}
                                className={styles.dangerButton}
                              >
                                Delete
                              </button>
                            </div>
                          </>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
