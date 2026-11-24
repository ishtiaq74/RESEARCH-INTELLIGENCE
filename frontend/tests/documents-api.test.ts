/**
 * Unit tests for document API client functions and error message mapping.
 *
 * All tests mock global `fetch` — no real HTTP requests are made.  This
 * keeps tests fast and independent of the backend being present on the
 * t3-frontend branch (the actual endpoints live on t3-upload which is not
 * merged to main yet).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiClientError,
  deleteDocument,
  documentUploadErrorMessage,
  listDocuments,
  uploadDocument,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeResponse(
  status: number,
  body: unknown = null,
  contentType = "application/json"
): Response {
  const bodyStr = body === null ? "" : JSON.stringify(body);
  return new Response(bodyStr || null, {
    status,
    headers: { "Content-Type": contentType },
  });
}

// ---------------------------------------------------------------------------
// documentUploadErrorMessage
// ---------------------------------------------------------------------------

describe("documentUploadErrorMessage", () => {
  it("returns fixed string for 409 Conflict (duplicate)", () => {
    const err = new ApiClientError("some server detail", 409);
    expect(documentUploadErrorMessage(err)).toBe(
      "Already uploaded in this project."
    );
  });

  it("returns fixed string for 413 Too Large", () => {
    const err = new ApiClientError("some server detail", 413);
    expect(documentUploadErrorMessage(err)).toBe("Larger than 20 MB.");
  });

  it("returns fixed string for 415 Unsupported Media Type", () => {
    const err = new ApiClientError("some server detail", 415);
    expect(documentUploadErrorMessage(err)).toBe("Not a PDF.");
  });

  it("returns server detail text for 422 (corrupt, too many pages, limit, etc.)", () => {
    const err = new ApiClientError("Document is encrypted.", 422);
    expect(documentUploadErrorMessage(err)).toBe("Document is encrypted.");
  });

  it("falls back for 422 when server detail is empty", () => {
    const err = new ApiClientError("", 422);
    expect(documentUploadErrorMessage(err)).toBe("File rejected by the server.");
  });

  it("returns fixed string for 404 Not Found", () => {
    const err = new ApiClientError("some server detail", 404);
    expect(documentUploadErrorMessage(err)).toBe(
      "Project or document not found."
    );
  });

  it("returns fixed string for 401 Unauthorized", () => {
    const err = new ApiClientError("some server detail", 401);
    expect(documentUploadErrorMessage(err)).toBe(
      "Authentication required. Please sign in."
    );
  });

  it("returns server message for unknown status codes", () => {
    const err = new ApiClientError("Internal server error.", 500);
    expect(documentUploadErrorMessage(err)).toBe("Internal server error.");
  });

  it("falls back for unknown status when message is empty", () => {
    const err = new ApiClientError("", 503);
    expect(documentUploadErrorMessage(err)).toBe(
      "Upload failed. Please try again."
    );
  });
});

// ---------------------------------------------------------------------------
// listDocuments
// ---------------------------------------------------------------------------

describe("listDocuments", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs /projects/{id}/documents and returns the list", async () => {
    const documents = [
      {
        id: 1,
        project_id: 10,
        original_filename: "paper.pdf",
        size_bytes: 1024,
        page_count: 5,
        status: "uploaded",
        created_at: "2026-11-01T00:00:00Z",
      },
    ];
    vi.mocked(fetch).mockResolvedValue(makeResponse(200, documents));

    const result = await listDocuments(10);

    expect(fetch).toHaveBeenCalledOnce();
    const [url] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/projects/10/documents");
    expect(result).toEqual(documents);
  });

  it("throws ApiClientError with status 401 when unauthenticated", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(401, { detail: "Not authenticated" })
    );

    await expect(listDocuments(10)).rejects.toMatchObject({
      status: 401,
    });
  });

  it("throws ApiClientError with status 404 when project not found", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(404, { detail: "Project not found." })
    );

    await expect(listDocuments(99)).rejects.toMatchObject({
      status: 404,
    });
  });
});

// ---------------------------------------------------------------------------
// uploadDocument
// ---------------------------------------------------------------------------

describe("uploadDocument", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs with FormData body (not a string) so Content-Type is NOT manually set", async () => {
    const doc = {
      id: 2,
      project_id: 10,
      original_filename: "research.pdf",
      size_bytes: 2048,
      page_count: 10,
      status: "uploaded",
      created_at: "2026-11-01T00:00:00Z",
    };
    vi.mocked(fetch).mockResolvedValue(makeResponse(201, doc));

    const file = new File(["pdf content"], "research.pdf", {
      type: "application/pdf",
    });
    const result = await uploadDocument(10, file);

    expect(fetch).toHaveBeenCalledOnce();
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    // Body must be FormData, not a string — apiRequest only sets Content-Type
    // for string bodies, ensuring the browser sets the multipart boundary.
    expect(init.body).toBeInstanceOf(FormData);
    // Verify Content-Type is NOT manually set (would break multipart boundary)
    const headers = new Headers(init.headers);
    expect(headers.has("Content-Type")).toBe(false);
    expect(result).toEqual(doc);
  });

  it("appends the file under field name 'file'", async () => {
    const doc = {
      id: 3,
      project_id: 10,
      original_filename: "paper.pdf",
      size_bytes: 500,
      page_count: null,
      status: "uploaded",
      created_at: "2026-11-01T00:00:00Z",
    };
    vi.mocked(fetch).mockResolvedValue(makeResponse(201, doc));

    const file = new File(["data"], "paper.pdf", { type: "application/pdf" });
    await uploadDocument(10, file);

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const form = init.body as FormData;
    expect(form.get("file")).toBe(file);
  });

  it("throws ApiClientError 409 for duplicate file", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(409, { detail: "Document already exists in this project." })
    );
    const file = new File(["data"], "dup.pdf", { type: "application/pdf" });

    await expect(uploadDocument(10, file)).rejects.toMatchObject({
      status: 409,
    });
  });

  it("throws ApiClientError 413 for oversized file", async () => {
    vi.mocked(fetch).mockResolvedValue(makeResponse(413, null, "text/plain"));
    const file = new File(["data"], "big.pdf", { type: "application/pdf" });

    await expect(uploadDocument(10, file)).rejects.toMatchObject({
      status: 413,
    });
  });

  it("throws ApiClientError 415 for non-PDF", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(415, { detail: "Only PDF files are accepted." })
    );
    const file = new File(["data"], "image.png", { type: "image/png" });

    await expect(uploadDocument(10, file)).rejects.toMatchObject({
      status: 415,
    });
  });

  it("throws ApiClientError 422 for corrupt PDF", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(422, { detail: "PDF is encrypted or corrupt." })
    );
    const file = new File(["bad"], "corrupt.pdf", {
      type: "application/pdf",
    });

    await expect(uploadDocument(10, file)).rejects.toMatchObject({
      status: 422,
      message: "PDF is encrypted or corrupt.",
    });
  });
});

// ---------------------------------------------------------------------------
// deleteDocument
// ---------------------------------------------------------------------------

describe("deleteDocument", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("DELETEs /projects/{pid}/documents/{did} and resolves to undefined on 204", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));

    const result = await deleteDocument(10, 1);

    expect(fetch).toHaveBeenCalledOnce();
    const [url] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/projects/10/documents/1");
    expect(result).toBeUndefined();
  });

  it("throws ApiClientError 404 when document not found", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(404, { detail: "Document not found." })
    );

    await expect(deleteDocument(10, 999)).rejects.toMatchObject({
      status: 404,
    });
  });

  it("throws ApiClientError 401 when not authenticated", async () => {
    vi.mocked(fetch).mockResolvedValue(
      makeResponse(401, { detail: "Not authenticated" })
    );

    await expect(deleteDocument(10, 1)).rejects.toMatchObject({
      status: 401,
    });
  });
});
