import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "@/features/auth/login-page";

const login = vi.fn();

vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ user: null, isAuthenticated: false, isBusy: false, login, logout: vi.fn() }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><LoginPage /></MemoryRouter></QueryClientProvider>);
}

describe("LoginPage", () => {
  beforeEach(() => login.mockReset());

  it("shows accessible validation for missing credentials", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("can reveal the password and submits credentials", async () => {
    login.mockResolvedValue(undefined);
    renderPage();
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "person@example.org" } });
    fireEvent.change(password, { target: { value: "synthetic-password" } });
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    await waitFor(() => expect(login).toHaveBeenCalledWith("person@example.org", "synthetic-password"));
  });
});
