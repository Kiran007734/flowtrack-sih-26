import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/api/client";
import { SignUpPage } from "@/features/auth/sign-up-page";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, register: vi.fn() } };
});

const registerAccount = vi.mocked(api.register);

function renderPage() {
  return render(<MemoryRouter><SignUpPage /></MemoryRouter>);
}

describe("SignUpPage", () => {
  beforeEach(() => registerAccount.mockReset());

  it("validates password confirmation before calling the API", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText("Enter your full name.")).toBeInTheDocument();
    expect(screen.getByText("Use at least 12 characters for your password.")).toBeInTheDocument();
    expect(registerAccount).not.toHaveBeenCalled();
  });

  it("submits a real account request and explains approval", async () => {
    registerAccount.mockResolvedValue({
      status: "PENDING_ADMINISTRATOR_APPROVAL",
      message: "Your account request was received. An administrator must approve it before you can sign in.",
    });
    renderPage();
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Synthetic User" } });
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "synthetic.user@example.org" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "synthetic-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "synthetic-password" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(await screen.findByText(/account request was received/i)).toBeInTheDocument();
    expect(registerAccount).toHaveBeenCalledWith({
      display_name: "Synthetic User",
      email: "synthetic.user@example.org",
      password: "synthetic-password",
    });
  });
});
