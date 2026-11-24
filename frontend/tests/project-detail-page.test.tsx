import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectDetailPage from "@/app/projects/[projectId]/page";
import {
  ApiClientError,
  getMe,
  listDocuments,
  logout,
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
let mockParams: { projectId: string } = { projectId: "10" };

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  useParams: () => mockParams,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getMe: vi.fn(),
    listDocuments: vi.fn(),
    logout: vi.fn(),
  };
});

describe("ProjectDetailPage (T3.2c list view)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockParams = { projectId: "10" };
  });

  afterEach(() => {
    cleanup();
  });

  it("shows loading state while fetching documents", () => {
    vi.mocked(getMe).mockReturnValue(new Promise(() => {}));
    vi.mocked(listDocuments).mockReturnValue(new Promise(() => {}));

    render(<ProjectDetailPage />);

    expect(screen.getByText(/loading project documents/i)).toBeDefined();
  });

  it("shows empty state and back link when project has no documents", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockResolvedValue([]);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText(/no documents yet/i)).toBeDefined();
    });

    const backLink = screen.getByRole("link", { name: /back to projects/i });
    expect(backLink.getAttribute("href")).toBe("/projects");
  });

  it("shows project-not-found state on 404 without leaking details", async () => {
    vi.mocked(getMe).mockResolvedValueOnce({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockRejectedValueOnce(
      new ApiClientError("Project not found.", 404)
    );

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/project not found or you do not have access/i)
      ).toBeDefined();
    });
  });

  it("shows project-not-found immediately for invalid non-numeric projectId", () => {
    mockParams = { projectId: "not-a-number" };

    render(<ProjectDetailPage />);

    expect(
      screen.getByText(/project not found or you do not have access/i)
    ).toBeDefined();
    expect(listDocuments).not.toHaveBeenCalled();
  });

  it("shows error state and recovers on Retry", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockRejectedValueOnce(
      new ApiClientError("Internal server error.", 500)
    );

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Internal server error.")).toBeDefined();
    });

    vi.mocked(listDocuments).mockResolvedValueOnce([
      {
        id: 1,
        project_id: 10,
        original_filename: "recovered.pdf",
        size_bytes: 2 * 1024 * 1024,
        page_count: 12,
        status: "uploaded",
        created_at: "2026-11-20T00:00:00Z",
      },
    ]);

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByText("recovered.pdf")).toBeDefined();
    });
  });

  it("renders document list with MB size, pages or '-' when null, status, date, and no download links", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "alice@example.com" });
    vi.mocked(listDocuments).mockResolvedValue([
      {
        id: 1,
        project_id: 10,
        original_filename: "attention.pdf",
        size_bytes: 1_572_864, // 1.50 MB
        page_count: 15,
        status: "uploaded",
        created_at: "2026-11-20T00:00:00Z",
      },
      {
        id: 2,
        project_id: 10,
        original_filename: "unprobed.pdf",
        size_bytes: 524_288, // 0.50 MB
        page_count: null,
        status: "processing",
        created_at: "2026-11-21T00:00:00Z",
      },
    ]);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("attention.pdf")).toBeDefined();
      expect(screen.getByText("1.50 MB")).toBeDefined();
      expect(screen.getByText("15")).toBeDefined();
      expect(screen.getByText("uploaded")).toBeDefined();

      expect(screen.getByText("unprobed.pdf")).toBeDefined();
      expect(screen.getByText("0.50 MB")).toBeDefined();
      expect(screen.getByText("-")).toBeDefined();
      expect(screen.getByText("processing")).toBeDefined();
    });

    // Must not render any download or preview links for documents
    const links = screen.getAllByRole("link");
    expect(links.every((link) => link.getAttribute("href") === "/projects")).toBe(
      true
    );
  });

  it("redirects to /login on 401", async () => {
    vi.mocked(getMe).mockRejectedValue(
      new ApiClientError("Not authenticated", 401)
    );

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });

  it("renders dangerous filename as plain text without HTML injection", async () => {
    const xssFilename = "<img src=x onerror=alert(1)>.pdf";
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "alice@example.com" });
    vi.mocked(listDocuments).mockResolvedValue([
      {
        id: 3,
        project_id: 10,
        original_filename: xssFilename,
        size_bytes: 1024,
        page_count: 1,
        status: "uploaded",
        created_at: "2026-11-20T00:00:00Z",
      },
    ]);

    const { container } = render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText(xssFilename)).toBeDefined();
    });

    expect(container.querySelector("img")).toBeNull();
  });

  it("signs out cleanly and clears document state", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "alice@example.com" });
    vi.mocked(listDocuments).mockResolvedValue([
      {
        id: 1,
        project_id: 10,
        original_filename: "secret.pdf",
        size_bytes: 1024,
        page_count: 2,
        status: "uploaded",
        created_at: "2026-11-20T00:00:00Z",
      },
    ]);
    vi.mocked(logout).mockResolvedValue(undefined);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("secret.pdf")).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /^sign out$/i }));

    await waitFor(() => {
      expect(logout).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/login");
      expect(screen.queryByText("secret.pdf")).toBeNull();
    });
  });
});
