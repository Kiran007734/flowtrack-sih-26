import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GuidanceWorkspacePage } from "@/features/catalogue/guidance-workspace-page";

const { api } = vi.hoisted(() => ({
  api: {
    guidanceSources: vi.fn(),
    catalogueRequirements: vi.fn(),
    requirementMappings: vi.fn(),
  },
}));

vi.mock("@/api/client", () => ({
  api,
  ApiError: class ApiError extends Error {},
}));
vi.mock("@/features/auth/auth-context", () => ({
  useAuth: () => ({
    user: { permissions: ["guidance.read"], roles: [] },
  }),
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <GuidanceWorkspacePage />
    </QueryClientProvider>,
  );
}

describe("GuidanceWorkspacePage", () => {
  it("renders an explicit empty state for a permitted reader", async () => {
    api.guidanceSources.mockResolvedValueOnce([]);
    api.catalogueRequirements.mockResolvedValueOnce([]);
    api.requirementMappings.mockResolvedValueOnce([]);
    renderPage();
    expect(
      await screen.findByText("No authorized guidance sources."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No mappings in your authorized scope."),
    ).toBeInTheDocument();
  });
});
