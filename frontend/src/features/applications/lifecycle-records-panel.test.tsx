import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LifecycleRecordsPanel } from "@/features/applications/lifecycle-records-panel";

const { api } = vi.hoisted(() => ({
  api: {
    committeeReviews: vi.fn(),
    committeeReview: vi.fn(),
    decisions: vi.fn(),
    communications: vi.fn(),
    createCommitteeReview: vi.fn(),
    assignCommitteeMember: vi.fn(),
    submitCommitteeReview: vi.fn(),
    finalizeCommitteeReview: vi.fn(),
    createDecision: vi.fn(),
    createCommunication: vi.fn(),
    updateCommunication: vi.fn(),
    approveCommunication: vi.fn(),
  },
}));

vi.mock("@/api/client", () => ({
  api,
  ApiError: class ApiError extends Error {},
}));

function renderPanel(overrides: Partial<React.ComponentProps<typeof LifecycleRecordsPanel>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><LifecycleRecordsPanel applicationId="application-1" stageKey="scrutiny" rowVersion={3} currentUserId="reviewer-1" canManageCommittee={false} canSubmitCommittee={false} canFinalizeCommittee={false} canDecide={false} canManageCommunication canApproveCommunication={false} {...overrides} /></QueryClientProvider>);
}

describe("LifecycleRecordsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.committeeReviews.mockResolvedValue([]);
    api.decisions.mockResolvedValue([]);
    api.communications.mockResolvedValue([]);
    api.createCommunication.mockResolvedValue({ id: "draft-2" });
    api.updateCommunication.mockResolvedValue({ id: "draft-1" });
  });

  it("edits an existing communication draft through the API", async () => {
    api.communications.mockResolvedValue([{ id: "draft-1", subject: "Initial subject", body: "Initial message", status: "DRAFT" }]);
    renderPanel();
    await screen.findByText("Initial subject");
    fireEvent.click(screen.getByRole("button", { name: "Edit draft" }));
    fireEvent.change(screen.getByLabelText("Communication subject"), { target: { value: "Updated subject" } });
    fireEvent.change(screen.getByLabelText("Message body"), { target: { value: "Updated message" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(api.updateCommunication).toHaveBeenCalledWith("draft-1", { subject: "Updated subject", body: "Updated message" }));
  });

  it("submits findings only for an assigned committee member", async () => {
    api.committeeReviews.mockResolvedValue([{ id: "review-1", stage_key: "scrutiny", committee_type: "SYNTHETIC_PANEL", status: "OPEN" }]);
    api.committeeReview.mockResolvedValue({ id: "review-1", application_id: "application-1", stage_key: "scrutiny", status: "OPEN", members: [{ id: "member-1", user_id: "reviewer-1", is_active: true }], submissions: [] });
    api.submitCommitteeReview.mockResolvedValue({ id: "submission-1" });
    renderPanel({ canManageCommunication: false, canSubmitCommittee: true });
    const findings = await screen.findByLabelText("Committee findings");
    fireEvent.change(findings, { target: { value: "The review contains sufficient findings." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit findings" }));
    await waitFor(() => expect(api.submitCommitteeReview).toHaveBeenCalledWith("review-1", { recommendation: "RECOMMEND_APPROVAL", findings: "The review contains sufficient findings." }));
  });
});
