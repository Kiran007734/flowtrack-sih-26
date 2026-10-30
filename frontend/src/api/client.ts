import type {
  Application,
  ApplicationHistoryEntry,
  AuditEvent,
  DocumentRecord,
  Deficiency,
  ReviewerAssignment,
  Institution,
  Notification,
  Page,
  TransitionOption,
  User,
  UserAdmin,
  EvcEvidence,
  EvcVisit,
  EvcVisitDetail,
  ComplianceObligation,
  ValidityRecord,
  PendencyDashboard,
  GuidanceSource,
  GuidanceVersion,
  GuidanceExtractionRun,
  CatalogueRequirement,
  RequirementEvidenceMapping,
} from "@/types/domain";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
const API_BASE_URL = configuredBaseUrl || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly fieldErrors?: Record<string, string[]>;

  constructor(message: string, status: number, code?: string, fieldErrors?: Record<string, string[]>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

interface ProblemResponse {
  detail?: string;
  title?: string;
  code?: string;
  errors?: Record<string, string[]>;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  user?: User;
}

interface RegistrationResponse {
  status: "PENDING_ADMINISTRATOR_APPROVAL";
  message: string;
}

const ACCESS_TOKEN_STORAGE_KEY = "flowtrack.access-token";

function readStoredAccessToken(): string | null {
  try {
    return window.sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
    return null;
  }
}

let accessToken: string | null = typeof window === "undefined" ? null : readStoredAccessToken();

export function setAccessToken(token: string | null): void {
  // Keep the token only for this browser tab so a refresh can restore a valid
  // session, while closing the tab clears it. It is never written to localStorage.
  accessToken = token;
  try {
    if (token) window.sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
    else window.sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  } catch {
    // The in-memory session still works when browser storage is unavailable.
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  // RFC 7807 errors use application/problem+json, which is JSON too.
  const isJson = response.headers.get("content-type")?.toLowerCase().includes("json");
  return (isJson ? response.json() : response.text()) as Promise<T>;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");
  if (["POST", "PATCH", "PUT", "DELETE"].includes((init.method ?? "GET").toUpperCase()) && !headers.has("Idempotency-Key")) {
    headers.set("Idempotency-Key", crypto.randomUUID());
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Unable to reach FlowTrack. Check that the API is running and try again.", 0, "NETWORK_ERROR");
  }

  if (!response.ok) {
    let problem: ProblemResponse = {};
    try {
      problem = await readResponse<ProblemResponse>(response);
    } catch {
      // Keep a safe, generic error if a gateway or proxy returns non-JSON content.
    }
    throw new ApiError(
      problem.detail || problem.title || "The request could not be completed.",
      response.status,
      problem.code,
      problem.errors,
    );
  }
  return readResponse<T>(response);
}

function toPage<T>(value: Page<T> | T[]): Page<T> {
  if (Array.isArray(value)) return { items: value };
  return { items: value.items ?? [], next_cursor: value.next_cursor };
}

export const api = {
  login: (email: string, password: string) => request<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (input: { display_name: string; email: string; password: string }) => request<RegistrationResponse>("/auth/register", { method: "POST", body: JSON.stringify(input) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<User>("/me"),
  users: (status?: string, query?: string) => request<UserAdmin[]>(`/users?${new URLSearchParams(Object.entries({ status: status ?? "", query: query ?? "" }).filter(([, value]) => Boolean(value)))}`),
  userAdministrationScopes: () => request<{ institutions: Array<{ id: string; name: string; region_id: string }>; regions: Array<{ id: string; name: string }> }>("/user-administration/scopes"),
  approveUser: (id: string, input: { role_key: string; scope_type: string; institution_id?: string; region_id?: string }) => request<UserAdmin>(`/users/${id}/approve`, { method: "POST", body: JSON.stringify(input) }),
  rejectUser: (id: string, reason: string) => request<UserAdmin>(`/users/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  setUserActivation: (id: string, is_active: boolean) => request<UserAdmin>(`/users/${id}/activation`, { method: "POST", body: JSON.stringify({ is_active }) }),
  assignUserRole: (id: string, input: { role_key: string; scope_type: string; institution_id?: string; region_id?: string }) => request(`/users/${id}/roles`, { method: "POST", body: JSON.stringify(input) }),
  revokeUserRole: (id: string, grantId: string) => request<void>(`/users/${id}/roles/${grantId}`, { method: "DELETE" }),
  institutions: async () => toPage(await request<Page<Institution> | Institution[]>("/institutions")),
  institution: (id: string) => request<Institution>(`/institutions/${id}`),
  applications: async (filters: { search?: string; institution_id?: string; status?: string; stage?: string; created_from?: string; created_to?: string; sort_by?: string; sort_direction?: "asc" | "desc"; cursor?: string; limit?: number } = {}) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, String(value)); });
    return toPage(await request<Page<Application> | Application[]>(`/applications${query.size ? `?${query}` : ""}`));
  },
  application: (id: string) => request<Application>(`/applications/${id}`),
  createApplication: (input: { institution_id: string; application_type: string; title: string; workflow_template_key?: string; data?: Record<string, unknown> }) => request<Application>("/applications", { method: "POST", body: JSON.stringify(input) }),
  updateApplication: (id: string, input: { application_type?: string; title?: string; data?: Record<string, unknown>; row_version: number }) => request<Application>(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  submitApplication: (id: string, rowVersion: number) => request<Application>(`/applications/${id}/submit`, { method: "POST", body: JSON.stringify({ row_version: rowVersion }) }),
  transitionApplication: (id: string, transitionKey: string, input: { row_version: number; comment?: string }) => request<Application>(`/applications/${id}/transitions/${transitionKey}`, { method: "POST", body: JSON.stringify(input) }),
  applicationTimeline: async (id: string) => toPage(await request<Page<ApplicationHistoryEntry> | ApplicationHistoryEntry[]>(`/applications/${id}/timeline`)),
  transitionOptions: async (id: string) => toPage(await request<Page<TransitionOption> | TransitionOption[]>(`/applications/${id}/transition-options`)),
  workflowTemplates: () => request<Array<{ id: string; key: string; name: string; versions: Array<{ id: string; version_number: number; is_published: boolean; route_type: string }> }>>("/workflow-templates"),
  createWorkflowVersion: (templateId: string, input: { route_type: string; source_reference?: string; stages: Array<{ key: string; display_name: string; ordinal: number; is_initial: boolean; entry_prerequisites: string[] }>; transitions: Array<{ key: string; from_stage_key: string; to_stage_key: string; required_permission: string; authorized_role_keys: string[]; prerequisites: Record<string, unknown>; blocking_conditions: Record<string, unknown>; explanation: string }> }) => request(`/workflow-templates/${templateId}/versions`, { method: "POST", body: JSON.stringify(input) }),
  publishWorkflowVersion: (id: string) => request(`/workflow-versions/${id}/publish`, { method: "POST" }),
  committeeReviews: (applicationId: string) => request<Array<{ id: string; stage_key: string; committee_type: string; status: string; outcome?: string | null; outcome_reason?: string | null }>>(`/applications/${applicationId}/committee-reviews`),
  committeeReview: (id: string) => request<{ id: string; application_id: string; stage_key: string; status: string; outcome?: string | null; members: Array<{ id: string; user_id: string; is_active: boolean }>; submissions: Array<{ id: string; member_id: string; recommendation: string; findings: string; submitted_at: string }> }>(`/committee-reviews/${id}`),
  createCommitteeReview: (applicationId: string, input: { stage_key: string; committee_type: string }) => request(`/applications/${applicationId}/committee-reviews`, { method: "POST", body: JSON.stringify(input) }),
  assignCommitteeMember: (reviewId: string, userId: string) => request(`/committee-reviews/${reviewId}/members`, { method: "POST", body: JSON.stringify({ user_id: userId }) }),
  submitCommitteeReview: (reviewId: string, input: { recommendation: string; findings: string }) => request(`/committee-reviews/${reviewId}/submissions`, { method: "POST", body: JSON.stringify(input) }),
  finalizeCommitteeReview: (reviewId: string, input: { outcome: string; reason: string }) => request(`/committee-reviews/${reviewId}/finalize`, { method: "POST", body: JSON.stringify(input) }),
  decisions: (applicationId: string) => request<Array<{ id: string; workflow_stage_key: string; outcome: string; rationale: string; decided_at: string }>>(`/applications/${applicationId}/decisions`),
  createDecision: (applicationId: string, input: { outcome: string; rationale: string; row_version: number }) => request(`/applications/${applicationId}/decisions`, { method: "POST", body: JSON.stringify(input) }),
  communications: (applicationId: string) => request<Array<{ id: string; decision_id?: string | null; subject: string; body: string; status: string; dispatched_at?: string | null }>>(`/applications/${applicationId}/communications`),
  createCommunication: (applicationId: string, input: { decision_id?: string; subject: string; body: string }) => request(`/applications/${applicationId}/communications`, { method: "POST", body: JSON.stringify(input) }),
  updateCommunication: (id: string, input: { decision_id?: string; subject: string; body: string }) => request(`/communications/${id}`, { method: "PUT", body: JSON.stringify(input) }),
  approveCommunication: (id: string) => request(`/communications/${id}/approve-and-queue`, { method: "POST" }),
  uploadDocument: async (input: { applicationId: string; file: File; classification: string }) => {
    const body = new FormData();
    body.append("application_id", input.applicationId);
    body.append("classification", input.classification);
    body.append("file", input.file);
    return request<DocumentRecord>("/documents/uploads", { method: "POST", body });
  },
  document: (id: string) => request<DocumentRecord>(`/documents/${id}`),
  downloadDocument: async (id: string) => {
    const headers = new Headers();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    const response = await fetch(`${API_BASE_URL}/documents/${id}/content`, { headers });
    if (!response.ok) throw new ApiError("The document could not be downloaded.", response.status);
    return response.blob();
  },
  notifications: async () => toPage(await request<Page<Notification> | Notification[]>("/notifications")),
  notification: (id: string) => request<Notification>(`/notifications/${id}`),
  markNotificationRead: (id: string) => request<Notification>(`/notifications/${id}/read`, { method: "POST" }),
  auditEvents: async () => toPage(await request<Page<AuditEvent> | AuditEvent[]>("/audit-events")),
  deficiencies: async (applicationId: string) => toPage(await request<Page<Deficiency> | Deficiency[]>(`/applications/${applicationId}/deficiencies`)),
  saveScrutinyReview: (applicationId: string, input: { summary?: string; findings: Array<{ requirement_reference: string; assessment: "ADEQUATE" | "INADEQUATE" | "CLARIFICATION_REQUIRED"; comment: string; references?: Record<string, string> }> }) => request(`/applications/${applicationId}/scrutiny-reviews`, { method: "POST", body: JSON.stringify(input) }),
  respondToDeficiency: (id: string, input: { response_text: string; document_id?: string }) => request<Deficiency>(`/deficiencies/${id}/responses`, { method: "POST", body: JSON.stringify(input) }),
  reviewerAssignments: async (applicationId: string) => toPage(await request<Page<ReviewerAssignment> | ReviewerAssignment[]>(`/applications/${applicationId}/reviewer-assignments`)),
  assignReviewer: (applicationId: string, input: { reviewer_id: string; reason?: string }) => request<ReviewerAssignment>(`/applications/${applicationId}/reviewer-assignments`, { method: "POST", body: JSON.stringify(input) }),
  evcVisits: (filters: { status?: string; institutionId?: string; regionId?: string } = {}) => {
    const query = new URLSearchParams();
    if (filters.status) query.set("status", filters.status);
    if (filters.institutionId) query.set("institution_id", filters.institutionId);
    if (filters.regionId) query.set("region_id", filters.regionId);
    return request<EvcVisit[]>(`/evc-visits${query.size ? `?${query}` : ""}`);
  },
  evcVisit: (id: string) => request<EvcVisitDetail>(`/evc-visits/${id}`),
  evcVisitAction: (id: string, action: string, rowVersion: number, reason?: string) => request<EvcVisit>(`/evc-visits/${id}/actions/${action}`, { method: "POST", body: JSON.stringify({ row_version: rowVersion, reason }) }),
  completeEvcChecklist: (id: string, note?: string) => request(`/evc-checklist-items/${id}/complete`, { method: "POST", body: JSON.stringify({ note }) }),
  submitEvcReport: (visitId: string, summary: string) => request<{ id: string; status: string }>(`/evc-visits/${visitId}/reports`, { method: "POST", body: JSON.stringify({ summary }) }),
  evcReportAction: (id: string, action: string, reason?: string) => request<{ id: string; status: string }>(`/evc-reports/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),
  verifyEvcEvidence: (id: string, action: "verify" | "reject", reason?: string) => request<EvcEvidence>(`/evc-evidence/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),
  evcReminders: (visitId: string) => request<Array<{ id: string; kind: string; status: string; created_at: string; attempt_count: number }>>(`/evc-visits/${visitId}/reminders`),
  complianceObligations: () => request<ComplianceObligation[]>("/compliance-obligations"),
  validityRecords: () => request<ValidityRecord[]>("/validity-records"),
  createComplianceObligation: (input: { application_id: string; title: string; description?: string; due_at?: string; timezone: string; required_evidence: boolean }) => request<{ id: string; status: string }>("/compliance-obligations", { method: "POST", body: JSON.stringify(input) }),
  complianceObligation: (id: string) => request<{ id: string; title: string; status: string; due_at?: string | null; evidence: Array<{ id: string; status: string; document_id: string; document_version_id: string; comment?: string | null }>; history: Array<{ action: string; created_at: string; reason?: string | null }>; reminders: Array<{ kind: string; status: string; created_at: string; attempt_count: number }> }>(`/compliance-obligations/${id}`),
  submitComplianceEvidence: (id: string, input: { document_id: string; document_version_id: string; comment?: string }) => request(`/compliance-obligations/${id}/evidence`, { method: "POST", body: JSON.stringify(input) }),
  reviewComplianceEvidence: (id: string, action: string, reason?: string) => request(`/compliance-evidence/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),
  createValidityRecord: (input: { document_id: string; document_version_id: string; category: string; issue_date?: string; expiry_date?: string; advance_notice_days: number }) => request("/validity-records", { method: "POST", body: JSON.stringify(input) }),
  renewValidityRecord: (id: string, documentVersionId: string) => request(`/validity-records/${id}/renew`, { method: "POST", body: JSON.stringify({ row_version: 1, document_version_id: documentVersionId }) }),
  aiScrutinyAssist: (applicationId: string) => request<{ mode: string; non_binding: boolean; corpus_status: string; sources: Array<{ document_id: string; document_version_id: string; filename: string; page_or_section?: string | null; source_kind: string }>; source_backed_facts: { submitted_document_count: number; compliance_evidence_count: number; open_required_obligations: string[] }; suggestions: string[]; uncertainty: string[] }>(`/applications/${applicationId}/ai-scrutiny-assist`),
  pendencyDashboard: () => request<PendencyDashboard>("/dashboard/pendency"),
  guidanceSources: () => request<GuidanceSource[]>("/guidance-sources"),
  guidanceSource: (id: string) => request<GuidanceSource>(`/guidance-sources/${id}`),
  createGuidanceSource: (input: { key: string; title: string; source_type: string; issuing_organization?: string; source_reference?: string; version_label: string; verification_status: "SYNTHETIC_DEMONSTRATION" | "VERIFIED_OFFICIAL" }) => request<{ id: string; key: string; version: GuidanceVersion }>("/guidance-sources", { method: "POST", body: JSON.stringify(input) }),
  guidanceVersionAction: (id: string, action: string, reason?: string) => request<GuidanceVersion>(`/guidance-versions/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),
  indexGuidanceVersion: (id: string) => request<{ source_version_id: string; passage_count: number; index_version: number; mode: string }>(`/guidance-versions/${id}/index`, { method: "POST" }),
  guidanceSearch: (question: string, limit = 10) => request<{ mode: string; results: Array<{ passage_id: string; text: string; source_version_id: string; page_number: number; verification_status: string; relevance_method: string; lexical_score: number; semantic_score?: number | null }> }>(`/guidance-search?${new URLSearchParams({ question, limit: String(limit) })}`),
  startGuidanceIngestion: (sourceVersionId: string, input: { document_id: string; document_version_id: string; synchronous?: boolean }) => request<GuidanceExtractionRun>(`/guidance-versions/${sourceVersionId}/ingestions`, { method: "POST", body: JSON.stringify(input) }),
  guidanceIngestions: (sourceVersionId: string) => request<GuidanceExtractionRun[]>(`/guidance-versions/${sourceVersionId}/ingestions`),
  guidanceExtractionRun: (id: string) => request<GuidanceExtractionRun>(`/guidance-extraction-runs/${id}`),
  reviewGuidanceExtraction: (id: string, action: "approve" | "reject", reason?: string) => request<GuidanceExtractionRun>(`/guidance-extraction-runs/${id}/review`, { method: "POST", body: JSON.stringify({ action, reason }) }),
  correctGuidanceExtraction: (id: string, corrected_text: string, reason: string) => request<{ id: string; corrected_at?: string }>(`/guidance-extraction-pages/${id}/correction`, { method: "POST", body: JSON.stringify({ corrected_text, reason }) }),
  catalogueRequirements: (filters: { source_version_id?: string; category?: string; module_key?: string; status?: string } = {}) => { const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => Boolean(value)) as Array<[string, string]>); return request<CatalogueRequirement[]>(`/catalogue-requirements${query.size ? `?${query}` : ""}`); },
  catalogueRequirement: (id: string) => request<CatalogueRequirement>(`/catalogue-requirements/${id}`),
  createCatalogueRequirement: (input: { stable_identifier: string; source_version_id: string; title: string; description: string; category: string; module_key: string; section_reference?: string }) => request<CatalogueRequirement>("/catalogue-requirements", { method: "POST", body: JSON.stringify(input) }),
  catalogueRequirementAction: (id: string, action: string, reason?: string) => request<CatalogueRequirement>(`/catalogue-requirements/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),
  requirementMappings: (filters: { application_id?: string; requirement_id?: string } = {}) => { const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => Boolean(value)) as Array<[string, string]>); return request<RequirementEvidenceMapping[]>(`/requirement-evidence-mappings${query.size ? `?${query}` : ""}`); },
  requirementMappingHistory: (id: string) => request<Array<{ action: string; outcome: string; reason?: string | null; created_at: string }>>(`/requirement-evidence-mappings/${id}/history`),
  proposeRequirementMapping: (input: { requirement_id: string; application_id: string; document_id: string; document_version_id: string; explanation: string }) => request<RequirementEvidenceMapping>("/requirement-evidence-mappings", { method: "POST", body: JSON.stringify(input) }),
  requirementMappingAction: (id: string, action: string, reason?: string) => request<RequirementEvidenceMapping>(`/requirement-evidence-mappings/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) }),
};
