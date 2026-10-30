import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, setAccessToken } from "@/api/client";
import { AuthProvider, useAuth } from "@/features/auth/auth-context";

vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return { ...actual, api: { ...actual.api, me: vi.fn() } };
});

const getCurrentUser = vi.mocked(api.me);

function SessionProbe() {
  const { isAuthenticated, isRestoring, user } = useAuth();
  return <p>{isRestoring ? "restoring" : isAuthenticated ? `signed-in:${user?.email}` : "signed-out"}</p>;
}

describe("AuthProvider session restoration", () => {
  beforeEach(() => {
    getCurrentUser.mockReset();
    setAccessToken(null);
  });

  afterEach(() => setAccessToken(null));

  it("restores a valid per-tab session after a refresh", async () => {
    setAccessToken("synthetic-session-token");
    getCurrentUser.mockResolvedValue({
      id: "00000000-0000-0000-0000-000000000001",
      email: "restored@example.org",
      display_name: "Restored User",
      is_active: true,
      roles: ["INSTITUTION_APPLICANT"],
      permissions: ["application.read"],
    });

    render(<AuthProvider><SessionProbe /></AuthProvider>);
    expect(screen.getByText("restoring")).toBeInTheDocument();
    expect(await screen.findByText("signed-in:restored@example.org")).toBeInTheDocument();
    expect(getCurrentUser).toHaveBeenCalledTimes(1);
  });

  it("clears an invalid saved token instead of restoring access", async () => {
    setAccessToken("expired-synthetic-token");
    getCurrentUser.mockRejectedValue(new Error("expired"));

    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByText("signed-out")).toBeInTheDocument());
    expect(window.sessionStorage.getItem("flowtrack.access-token")).toBeNull();
  });
});
