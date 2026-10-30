import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/api/client";
import { UserManagementPage } from "@/features/admin/user-management-page";

const auth = vi.fn();

vi.mock("@/features/auth/auth-context", () => ({ useAuth: () => auth() }));
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, users: vi.fn(), userAdministrationScopes: vi.fn(), approveUser: vi.fn() } };
});

const users = vi.mocked(api.users);
const scopes = vi.mocked(api.userAdministrationScopes);
const approveUser = vi.mocked(api.approveUser);

function renderPage() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><UserManagementPage /></MemoryRouter></QueryClientProvider>);
}

describe("UserManagementPage", () => {
  beforeEach(() => {
    users.mockReset(); scopes.mockReset(); approveUser.mockReset();
    auth.mockReturnValue({ user: { permissions: ["user.manage"] } });
    scopes.mockResolvedValue({ institutions: [{ id: "institution-1", name: "Synthetic Institution", region_id: "region-1" }], regions: [{ id: "region-1", name: "Synthetic Region" }] });
  });

  it("shows pending requests and persists an approval through the API", async () => {
    const pending = { id: "user-1", email: "pending@example.org", display_name: "Pending User", is_active: false, roles: [], permissions: [], registration_status: "PENDING" as const, created_at: "2026-01-01T00:00:00Z", grants: [] };
    users.mockResolvedValue([pending]);
    approveUser.mockResolvedValue({ ...pending, is_active: true, registration_status: "APPROVED" });
    renderPage();
    expect(await screen.findByText("Pending User")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    fireEvent.change(screen.getByLabelText("Institution"), { target: { value: "institution-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve request" }));
    await waitFor(() => expect(approveUser).toHaveBeenCalledWith("user-1", expect.objectContaining({ role_key: "INSTITUTION_APPLICANT", institution_id: "institution-1" })));
  });

  it("does not render an authorized workspace without user.manage", () => {
    auth.mockReturnValue({ user: { permissions: [] } });
    renderPage();
    expect(screen.queryByText("User management")).not.toBeInTheDocument();
  });

  it("shows loading and server-error states", async () => {
    users.mockImplementation(() => new Promise(() => undefined));
    renderPage();
    expect(screen.getByText("Loading users…")).toBeInTheDocument();
  });

  it("shows a retryable server error", async () => {
    users.mockRejectedValue(new Error("server failure"));
    renderPage();
    expect(await screen.findByText(/Unable to load users/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
