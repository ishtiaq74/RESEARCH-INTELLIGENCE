import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";
import RegisterPage from "@/app/register/page";
import { ApiClientError, getMe, login, register } from "@/lib/api";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getMe: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
  };
});

describe("Auth pages (Register & Login)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("RegisterPage", () => {
    it("renders email and password inputs with labels and hint", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );

      render(<RegisterPage />);

      expect(screen.getByLabelText(/email address/i)).toBeDefined();
      expect(screen.getByLabelText(/^password/i)).toBeDefined();
      expect(
        screen.getByText(/must be 8 to 128 characters/i)
      ).toBeDefined();
      expect(
        screen.getByRole("button", { name: /create account/i })
      ).toBeDefined();
    });

    it("shows client validation hint on password length and blocks API call", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );

      render(<RegisterPage />);

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^password/i), {
        target: { value: "short" },
      });
      fireEvent.click(screen.getByRole("button", { name: /create account/i }));

      expect(
        screen.getByText(/password must be between 8 and 128 characters/i)
      ).toBeDefined();
      expect(register).not.toHaveBeenCalled();
    });

    it("calls register and navigates to /projects on success", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );
      vi.mocked(register).mockResolvedValue({
        id: 1,
        email: "newuser@example.com",
      });

      render(<RegisterPage />);

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "newuser@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^password/i), {
        target: { value: "validPassword123" },
      });
      fireEvent.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(register).toHaveBeenCalledWith(
          "newuser@example.com",
          "validPassword123"
        );
        expect(mockPush).toHaveBeenCalledWith("/projects");
      });
    });

    it("displays error in aria-live region when registration fails with 409", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );
      vi.mocked(register).mockRejectedValue(
        new ApiClientError("Email already registered.", 409)
      );

      render(<RegisterPage />);

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "existing@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^password/i), {
        target: { value: "validPassword123" },
      });
      fireEvent.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        const alert = screen.getByRole("alert");
        expect(alert.textContent).toContain("Email already registered.");
      });
    });

    it("redirects signed-in user away from register page using GET /auth/me", async () => {
      vi.mocked(getMe).mockResolvedValue({
        id: 5,
        email: "alreadyin@example.com",
      });

      render(<RegisterPage />);

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/projects");
      });
    });
  });

  describe("LoginPage", () => {
    it("renders email and password inputs with labels", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );

      render(<LoginPage />);

      expect(screen.getByLabelText(/email address/i)).toBeDefined();
      expect(screen.getByLabelText(/^password/i)).toBeDefined();
      expect(
        screen.getByRole("button", { name: /sign in/i })
      ).toBeDefined();
    });

    it("shows client validation hint on password length and blocks API call", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );

      render(<LoginPage />);

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^password/i), {
        target: { value: "123" },
      });
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      expect(
        screen.getByText(/password must be between 8 and 128 characters/i)
      ).toBeDefined();
      expect(login).not.toHaveBeenCalled();
    });

    it("calls login and navigates to /projects on success", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );
      vi.mocked(login).mockResolvedValue({
        id: 1,
        email: "user@example.com",
      });

      render(<LoginPage />);

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "user@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^password/i), {
        target: { value: "correctPassword123" },
      });
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(login).toHaveBeenCalledWith(
          "user@example.com",
          "correctPassword123"
        );
        expect(mockPush).toHaveBeenCalledWith("/projects");
      });
    });

    it("shows server's generic login message as is in aria-live region", async () => {
      vi.mocked(getMe).mockRejectedValue(
        new ApiClientError("Not authenticated", 401)
      );
      vi.mocked(login).mockRejectedValue(
        new ApiClientError("Invalid email or password.", 401)
      );

      render(<LoginPage />);

      fireEvent.change(screen.getByLabelText(/email address/i), {
        target: { value: "bad@example.com" },
      });
      fireEvent.change(screen.getByLabelText(/^password/i), {
        target: { value: "wrongPassword123" },
      });
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        const alert = screen.getByRole("alert");
        expect(alert.textContent).toContain("Invalid email or password.");
      });
    });

    it("redirects signed-in user away from login page using GET /auth/me", async () => {
      vi.mocked(getMe).mockResolvedValue({
        id: 3,
        email: "alreadyin@example.com",
      });

      render(<LoginPage />);

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/projects");
      });
    });
  });
});
