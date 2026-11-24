import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProjectDetailPage from "@/app/projects/[projectId]/page";
import {
  ApiClientError,
  deleteDocument,
  getMe,
  listDocuments,
  logout,
  uploadDocument,
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
    uploadDocument: vi.fn(),
    deleteDocument: vi.fn(),
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

describe("ProjectDetailPage (T3.2d upload flow)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockParams = { projectId: "10" };
  });

  afterEach(() => {
    cleanup();
  });

  it("uploads a valid PDF, disables the upload button while in flight, and refreshes the list", async () => {
    const uploadedDoc = {
      id: 99,
      project_id: 10,
      original_filename: "paper.pdf",
      size_bytes: 2 * 1024 * 1024,
      page_count: 8,
      status: "uploaded",
      created_at: "2026-11-25T00:00:00Z",
    };

    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([uploadedDoc]);

    let resolveUpload!: (doc: typeof uploadedDoc) => void;
    vi.mocked(uploadDocument).mockReturnValue(
      new Promise((resolve) => {
        resolveUpload = resolve;
      })
    );

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/select pdf file/i)).toBeDefined();
    });

    const uploadButton = screen.getByRole("button", { name: /^upload$/i }) as HTMLButtonElement;
    expect(uploadButton.disabled).toBe(true);

    const fileInput = screen.getByLabelText(/select pdf file/i) as HTMLInputElement;
    expect(fileInput.getAttribute("accept")).toBe("application/pdf,.pdf");
    expect(fileInput.multiple).toBe(false);

    const pdfFile = new File(["%PDF-1.4"], "paper.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(fileInput, { target: { files: [pdfFile] } });
    expect(uploadButton.disabled).toBe(false);

    fireEvent.click(uploadButton);

    await waitFor(() => {
      const busyButton = screen.getByRole("button", {
        name: /uploading/i,
      }) as HTMLButtonElement;
      expect(busyButton.disabled).toBe(true);
    });

    resolveUpload(uploadedDoc);

    await waitFor(() => {
      expect(uploadDocument).toHaveBeenCalledWith(10, pdfFile);
      expect(listDocuments).toHaveBeenCalledTimes(2);
      expect(screen.getByText("paper.pdf")).toBeDefined();
    });
  });

  it("rejects non-PDF files client-side without calling the API", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/select pdf file/i)).toBeDefined();
    });

    const fileInput = screen.getByLabelText(/select pdf file/i);
    const badFile = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.change(fileInput, { target: { files: [badFile] } });
    fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("Not a PDF.");
    });
    expect(uploadDocument).not.toHaveBeenCalled();
  });

  it("rejects files larger than 20 MB client-side without calling the API", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/select pdf file/i)).toBeDefined();
    });

    const fileInput = screen.getByLabelText(/select pdf file/i);
    const hugeFile = new File(["%PDF-1.4"], "huge.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(hugeFile, "size", { value: 20 * 1024 * 1024 + 1 });

    fireEvent.change(fileInput, { target: { files: [hugeFile] } });
    fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("Larger than 20 MB.");
    });
    expect(uploadDocument).not.toHaveBeenCalled();
  });

  it.each([
    [409, "duplicate", "Already uploaded in this project."],
    [413, "too large", "Larger than 20 MB."],
    [415, "wrong type", "Not a PDF."],
    [422, "PDF is encrypted.", "PDF is encrypted."],
    [404, "not found", "Project or document not found."],
  ])(
    "displays mapped error message for HTTP %i",
    async (status, serverDetail, expectedMessage) => {
      vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
      vi.mocked(listDocuments).mockResolvedValueOnce([]);
      vi.mocked(uploadDocument).mockRejectedValueOnce(
        new ApiClientError(serverDetail, status)
      );

      render(<ProjectDetailPage />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select pdf file/i)).toBeDefined();
      });

      const fileInput = screen.getByLabelText(/select pdf file/i);
      const pdfFile = new File(["%PDF-1.4"], "paper.pdf", {
        type: "application/pdf",
      });
      fireEvent.change(fileInput, { target: { files: [pdfFile] } });
      fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert").textContent).toBe(expectedMessage);
      });
    }
  );

  it("redirects to /login on 401 during upload", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockResolvedValueOnce([]);
    vi.mocked(uploadDocument).mockRejectedValueOnce(
      new ApiClientError("Not authenticated", 401)
    );

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/select pdf file/i)).toBeDefined();
    });

    const fileInput = screen.getByLabelText(/select pdf file/i);
    const pdfFile = new File(["%PDF-1.4"], "paper.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(fileInput, { target: { files: [pdfFile] } });
    fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });
});

describe("ProjectDetailPage (T3.2e delete flow)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockParams = { projectId: "10" };
  });

  afterEach(() => {
    cleanup();
  });

  it("requires two-step confirmation before deleting and removes document on 204", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockResolvedValueOnce([
      {
        id: 42,
        project_id: 10,
        original_filename: "to-delete.pdf",
        size_bytes: 1024,
        page_count: 3,
        status: "uploaded",
        created_at: "2026-11-25T00:00:00Z",
      },
    ]);
    vi.mocked(deleteDocument).mockResolvedValueOnce(undefined);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("to-delete.pdf")).toBeDefined();
    });

    // Step 1: click Delete -> should NOT delete immediately
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(deleteDocument).not.toHaveBeenCalled();
    expect(screen.getByText(/delete this document\?/i)).toBeDefined();

    // Cancel keeps the document
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByText("to-delete.pdf")).toBeDefined();
    expect(deleteDocument).not.toHaveBeenCalled();

    // Step 2: click Delete, then Confirm Delete
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /confirm delete/i })
    );

    await waitFor(() => {
      expect(deleteDocument).toHaveBeenCalledWith(10, 42);
      expect(screen.queryByText("to-delete.pdf")).toBeNull();
      expect(screen.getByText(/no documents yet/i)).toBeDefined();
    });
  });

  it("shows error message if delete fails and redirects on 401", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "user@example.com" });
    vi.mocked(listDocuments).mockResolvedValueOnce([
      {
        id: 43,
        project_id: 10,
        original_filename: "locked.pdf",
        size_bytes: 1024,
        page_count: 3,
        status: "uploaded",
        created_at: "2026-11-25T00:00:00Z",
      },
    ]);
    vi.mocked(deleteDocument)
      .mockRejectedValueOnce(new ApiClientError("Document not found.", 404))
      .mockRejectedValueOnce(new ApiClientError("Not authenticated", 401));

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("locked.pdf")).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /confirm delete/i })
    );

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("Document not found.");
    });

    fireEvent.click(
      await screen.findByRole("button", { name: /confirm delete/i })
    );

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/login");
    });
  });
});

describe("ProjectDetailPage (T3.2g state hygiene)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockParams = { projectId: "10" };
  });

  afterEach(() => {
    cleanup();
  });

  it("clears documents, selected file, upload error, and delete confirmation when navigating to another project", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, email: "alice@example.com" });
    vi.mocked(listDocuments)
      .mockResolvedValueOnce([
        {
          id: 1,
          project_id: 10,
          original_filename: "project-10.pdf",
          size_bytes: 1024,
          page_count: 4,
          status: "uploaded",
          created_at: "2026-11-25T00:00:00Z",
        },
      ])
      .mockResolvedValueOnce([
        {
          id: 2,
          project_id: 20,
          original_filename: "project-20.pdf",
          size_bytes: 2048,
          page_count: 7,
          status: "uploaded",
          created_at: "2026-11-25T00:00:00Z",
        },
      ]);

    const { rerender } = render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("project-10.pdf")).toBeDefined();
    });

    // Trigger an upload error and open delete confirmation on project 10
    const fileInput = screen.getByLabelText(/select pdf file/i);
    const badFile = new File(["hello"], "bad.txt", { type: "text/plain" });
    fireEvent.change(fileInput, { target: { files: [badFile] } });
    fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("Not a PDF.");
    });

    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(screen.getByText(/delete this document\?/i)).toBeDefined();

    // Navigate to project 20
    mockParams = { projectId: "20" };
    rerender(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("project-20.pdf")).toBeDefined();
    });

    expect(screen.queryByText("project-10.pdf")).toBeNull();
    expect(screen.queryByText("Not a PDF.")).toBeNull();
    expect(screen.queryByText(/delete this document\?/i)).toBeNull();
  });

  it("clears all state on sign-out and does not leak data or button state to next user", async () => {
    vi.mocked(getMe).mockResolvedValueOnce({
      id: 1,
      email: "alice@example.com",
    });
    vi.mocked(listDocuments).mockResolvedValueOnce([
      {
        id: 11,
        project_id: 10,
        original_filename: "alice-private.pdf",
        size_bytes: 1024,
        page_count: 2,
        status: "uploaded",
        created_at: "2026-11-25T00:00:00Z",
      },
    ]);
    vi.mocked(logout).mockResolvedValueOnce(undefined);

    const { unmount } = render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("alice@example.com")).toBeDefined();
      expect(screen.getByText("alice-private.pdf")).toBeDefined();
    });

    // Trigger upload error before signing out
    const fileInput = screen.getByLabelText(/select pdf file/i);
    const badFile = new File(["x"], "wrong.docx", { type: "text/plain" });
    fireEvent.change(fileInput, { target: { files: [badFile] } });
    fireEvent.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toBe("Not a PDF.");
    });

    fireEvent.click(screen.getByRole("button", { name: /^sign out$/i }));

    await waitFor(() => {
      expect(logout).toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledWith("/login");
      expect(screen.queryByText("alice@example.com")).toBeNull();
      expect(screen.queryByText("alice-private.pdf")).toBeNull();
      expect(screen.queryByText("Not a PDF.")).toBeNull();
    });

    unmount();

    // User B signs in and visits a project
    vi.mocked(getMe).mockResolvedValueOnce({
      id: 2,
      email: "bob@example.com",
    });
    vi.mocked(listDocuments).mockResolvedValueOnce([]);

    render(<ProjectDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("bob@example.com")).toBeDefined();
      const btn = screen.getByRole("button", { name: /^sign out$/i });
      expect(btn.textContent).toBe("Sign out");
      expect(screen.queryByText("alice-private.pdf")).toBeNull();
      expect(screen.queryByText("Not a PDF.")).toBeNull();
    });
  });
});
