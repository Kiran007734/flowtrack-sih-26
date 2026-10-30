import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RequireAuth } from "@/routes/require-auth";

vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({ isAuthenticated: false }),
}));

describe("RequireAuth", () => {
  it("redirects unauthenticated navigation to login", () => {
    render(<MemoryRouter initialEntries={["/protected"]}><Routes><Route path="/protected" element={<RequireAuth><p>protected content</p></RequireAuth>} /><Route path="/login" element={<p>login screen</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText("login screen")).toBeInTheDocument();
  });
});
