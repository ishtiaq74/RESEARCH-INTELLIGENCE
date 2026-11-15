import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectsPage from "@/app/projects/page";
import {
  ApiClientError,
  createProject,
  deleteProject,
  getMe,
  listProjects,
  logout,
  renameProject,
} from "@/lib/api";

const mockPush = vi.fn();
const mockRouter = {
  push: mockPush,
  replace: vi.fn(),
  refresh: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
};

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getMe: vi.fn(),
    listProjects: vi.fn(),
    createProject: vi.fn(),
    renameProject: vi.fn(),
    deleteProject: vi.fn(),
    logout: vi.fn(),
  };
});

describe("ProjectsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows loading state initially while fetching projects", async () => {
    vi.mocked(getMe).mockReturnValue(new Promise(() => {}));
    vi.mocked(listProjects).mockReturnValue(new Promise(() => {}));

    render(<ProjectsPage />);

    expect(
      screen.getByText(/loading your research projects/i)
    ).toBeDefined();
  });

  it("shows empty state when user has no projects", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([]);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText(/no projects yet/i)).toBeDefined();
      expect(
        screen.getByText(/create your first research project above/i)
      ).toBeDefined();
    });
  });

  it("shows error state when project loading fails and allows retry", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockRejectedValue(
      new ApiClientError("Database connection failed", 500)
    );

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("Database connection failed")).toBeDefined();
      expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
    });

    // Succeed on retry
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: 1,
        name: "Recovered Project",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      },
    ]);

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByText("Recovered Project")).toBeDefined();
    });
  });

  it("renders list state with projects and user email", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "researcher@lab.org",
    });
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: 101,
        name: "Transformer Architectures",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      },
      {
        id: 102,
        name: "Quantum Computing Algorithms",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      },
    ]);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("researcher@lab.org")).toBeDefined();
      expect(screen.getByText("Transformer Architectures")).toBeDefined();
      expect(screen.getByText("Quantum Computing Algorithms")).toBeDefined();
    });
  });

  it("creates a new project and appends it to the list", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([]);
    vi.mocked(createProject).mockResolvedValue({
      id: 201,
      name: "New Multimodal RAG",
      owner_id: 1,
      created_at: "2026-10-30T00:00:00Z",
      updated_at: "2026-10-30T00:00:00Z",
    });

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText(/no projects yet/i)).toBeDefined();
    });

    const input = screen.getByLabelText(/project name/i);
    fireEvent.change(input, { target: { value: "   New Multimodal RAG   " } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => {
      expect(createProject).toHaveBeenCalledWith("New Multimodal RAG");
      expect(screen.getByText("New Multimodal RAG")).toBeDefined();
    });
  });

  it("validates empty project name on create", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([]);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText(/no projects yet/i)).toBeDefined();
    });

    const input = screen.getByLabelText(/project name/i);
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.submit(input.closest("form")!);

    expect(screen.getByText(/project name cannot be empty/i)).toBeDefined();
    expect(createProject).not.toHaveBeenCalled();
  });

  it("handles inline rename with save and cancel", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: 301,
        name: "Initial Name",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      },
    ]);
    vi.mocked(renameProject).mockResolvedValue({
      id: 301,
      name: "Updated Name",
      owner_id: 1,
      created_at: "2026-10-30T00:00:00Z",
      updated_at: "2026-10-30T00:00:00Z",
    });

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("Initial Name")).toBeDefined();
    });

    // Click Rename
    fireEvent.click(screen.getByRole("button", { name: /^rename$/i }));

    // Rename input should appear
    const renameInput = await screen.findByLabelText(/rename project initial name/i);
    expect(renameInput).toBeDefined();

    // Cancel rename
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByText("Initial Name")).toBeDefined();

    // Open rename again and save
    fireEvent.click(screen.getByRole("button", { name: /^rename$/i }));
    const renameInput2 = await screen.findByLabelText(/rename project initial name/i);
    fireEvent.change(renameInput2, { target: { value: "Updated Name" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(renameProject).toHaveBeenCalledWith(301, "Updated Name");
      expect(screen.getByText("Updated Name")).toBeDefined();
    });
  });

  it("requires delete confirmation step before deleting project", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: 401,
        name: "Project To Delete",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      },
    ]);
    vi.mocked(deleteProject).mockResolvedValue(undefined);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("Project To Delete")).toBeDefined();
    });

    // Click Delete - should NOT immediately delete
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(deleteProject).not.toHaveBeenCalled();

    // Confirmation warning must be displayed
    expect(
      screen.getByText(/this cannot be undone/i)
    ).toBeDefined();

    // Cancel deletion
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByText("Project To Delete")).toBeDefined();
    expect(deleteProject).not.toHaveBeenCalled();

    // Click Delete again, then Confirm Delete
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const confirmButton = await screen.findByRole("button", { name: /confirm delete/i });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(deleteProject).toHaveBeenCalledWith(401);
      expect(screen.queryByText("Project To Delete")).toBeNull();
      expect(screen.getByText(/no projects yet/i)).toBeDefined();
    });
  });

  it("redirects to /login on 401 from any API call", async () => {
    vi.mocked(getMe).mockRejectedValue(
      new ApiClientError("Not authenticated", 401)
    );

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("signs out and redirects to /login when clicking sign-out button", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "user@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([]);
    vi.mocked(logout).mockResolvedValue(undefined);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /sign out/i })).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(logout).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("clears all page state on sign out and resets button to 'Sign out'", async () => {
    vi.mocked(getMe).mockResolvedValue({
      id: 1,
      email: "alice@example.com",
    });
    vi.mocked(listProjects).mockResolvedValue([
      {
        id: 501,
        name: "Alice's Secret Project",
        owner_id: 1,
        created_at: "2026-11-01T00:00:00Z",
        updated_at: "2026-11-01T00:00:00Z",
      },
    ]);
    vi.mocked(logout).mockResolvedValue(undefined);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("alice@example.com")).toBeDefined();
      expect(screen.getByText("Alice's Secret Project")).toBeDefined();
    });

    const signOutBtn = screen.getByRole("button", { name: /^sign out$/i });
    fireEvent.click(signOutBtn);

    await waitFor(() => {
      expect(logout).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/login");
      // State must be completely cleared
      expect(screen.queryByText("alice@example.com")).toBeNull();
      expect(screen.queryByText("Alice's Secret Project")).toBeNull();
    });
  });

  it("displays 'Sign out' button label (never 'Signing out…') after remounting with a new user", async () => {
    // 1. Initial user signs in
    vi.mocked(getMe).mockResolvedValueOnce({
      id: 1,
      email: "alice@example.com",
    });
    vi.mocked(listProjects).mockResolvedValueOnce([]);
    vi.mocked(logout).mockResolvedValue(undefined);

    const { unmount } = render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("alice@example.com")).toBeDefined();
    });

    // User signs out
    fireEvent.click(screen.getByRole("button", { name: /^sign out$/i }));
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });

    unmount();

    // 2. New user signs in and visits /projects
    vi.mocked(getMe).mockResolvedValueOnce({
      id: 2,
      email: "bob@example.com",
    });
    vi.mocked(listProjects).mockResolvedValueOnce([]);

    render(<ProjectsPage />);

    await waitFor(() => {
      expect(screen.getByText("bob@example.com")).toBeDefined();
      // Button label must be 'Sign out', NOT 'Signing out…'
      const btn = screen.getByRole("button", { name: /^sign out$/i });
      expect(btn.textContent).toBe("Sign out");
      expect(screen.queryByText("Signing out…")).toBeNull();
    });
  });
});
