import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiClientError,
  createProject,
  deleteProject,
  getMe,
  listProjects,
  login,
  logout,
  me,
  register,
  renameProject,
} from "@/lib/api";

describe("API client module", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("always includes credentials: 'include' on requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 1, email: "test@example.com" }),
    });
    global.fetch = fetchMock;

    await getMe();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.credentials).toBe("include");
  });

  it("calls register with POST /auth/register and credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 2, email: "user@example.com" }),
    });
    global.fetch = fetchMock;

    const result = await register("user@example.com", "securePassword123");

    expect(result).toEqual({ id: 2, email: "user@example.com" });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/register");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
    expect(JSON.parse(options.body)).toEqual({
      email: "user@example.com",
      password: "securePassword123",
    });
  });

  it("calls login with POST /auth/login and credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 1, email: "user@example.com" }),
    });
    global.fetch = fetchMock;

    const result = await login("user@example.com", "mypassword8");

    expect(result).toEqual({ id: 1, email: "user@example.com" });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/login");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
  });

  it("calls logout with POST /auth/logout and handles 204 No Content", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    });
    global.fetch = fetchMock;

    await logout();

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/logout");
    expect(options.method).toBe("POST");
    expect(options.credentials).toBe("include");
  });

  it("supports getMe and alias me", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 10, email: "alias@example.com" }),
    });
    global.fetch = fetchMock;

    const res1 = await getMe();
    const res2 = await me();

    expect(res1).toEqual({ id: 10, email: "alias@example.com" });
    expect(res2).toEqual({ id: 10, email: "alias@example.com" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("calls listProjects with query parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [
        {
          id: 1,
          name: "Project A",
          owner_id: 1,
          created_at: "2026-10-30T00:00:00Z",
          updated_at: "2026-10-30T00:00:00Z",
        },
      ],
    });
    global.fetch = fetchMock;

    const result = await listProjects({ limit: 10, offset: 20 });

    expect(result).toHaveLength(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects?limit=10&offset=20");
    expect(options.credentials).toBe("include");
  });

  it("calls createProject with POST /projects and payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: 3,
        name: "New Research",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      }),
    });
    global.fetch = fetchMock;

    const result = await createProject("New Research");

    expect(result.id).toBe(3);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ name: "New Research" });
  });

  it("calls renameProject with PATCH /projects/:id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: 7,
        name: "Renamed Project",
        owner_id: 1,
        created_at: "2026-10-30T00:00:00Z",
        updated_at: "2026-10-30T00:00:00Z",
      }),
    });
    global.fetch = fetchMock;

    const result = await renameProject(7, "Renamed Project");

    expect(result.name).toBe("Renamed Project");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/7");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ name: "Renamed Project" });
  });

  it("calls deleteProject with DELETE /projects/:id and handles 204", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    });
    global.fetch = fetchMock;

    await deleteProject(12);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/projects/12");
    expect(options.method).toBe("DELETE");
  });

  describe("error handling and status code mapping", () => {
    it("handles 401 on login and preserves server message as is", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Invalid email or password." }),
      });

      await expect(login("bad@example.com", "wrong")).rejects.toBeInstanceOf(
        ApiClientError
      );
      await expect(login("bad@example.com", "wrong")).rejects.toMatchObject({
        status: 401,
        message: "Invalid email or password.",
      });
    });

    it("handles 401 with default message when no server detail provided", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({}),
      });

      await expect(getMe()).rejects.toBeInstanceOf(ApiClientError);
      await expect(getMe()).rejects.toMatchObject({
        status: 401,
        message: "Authentication required. Please sign in.",
      });
    });

    it("handles 404 Project Not Found", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: "Project not found." }),
      });

      await expect(renameProject(999, "Missing")).rejects.toBeInstanceOf(
        ApiClientError
      );
      await expect(renameProject(999, "Missing")).rejects.toMatchObject({
        status: 404,
        message: "Project not found.",
      });
    });

    it("handles 409 Email already registered", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: "Email already registered." }),
      });

      await expect(
        register("exists@example.com", "password123")
      ).rejects.toBeInstanceOf(ApiClientError);
      await expect(
        register("exists@example.com", "password123")
      ).rejects.toMatchObject({
        status: 409,
        message: "Email already registered.",
      });
    });

    it("handles 422 with FastAPI validation error array", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [{ msg: "String should have at least 1 character" }],
        }),
      });

      await expect(createProject("")).rejects.toBeInstanceOf(ApiClientError);
      await expect(createProject("")).rejects.toMatchObject({
        status: 422,
        message: "String should have at least 1 character",
      });
    });

    it("handles network failure / connection refused gracefully", async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error("Failed to fetch"));

      await expect(getMe()).rejects.toBeInstanceOf(ApiClientError);
      await expect(getMe()).rejects.toMatchObject({
        status: 0,
        message:
          "Unable to connect to the server. Please ensure the backend is running.",
      });
    });
  });
});
