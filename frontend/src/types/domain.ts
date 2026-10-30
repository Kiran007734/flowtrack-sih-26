export type RoleKey =
  | "INSTITUTION_APPLICANT"
  | "INSTITUTION_ADMINISTRATOR"
  | "SCRUTINY_OFFICER"
  | "REGIONAL_OFFICER"
  | "REGIONAL_ADMINISTRATOR"
  | "EVC_MEMBER"
  | "EVC_COORDINATOR"
  | "AUTHORIZED_REVIEWER"
  | "COMPLIANCE_OFFICER"
  | "SYSTEM_ADMINISTRATOR"
  | "READ_ONLY_AUDITOR";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  roles: RoleKey[];
  permissions: string[];
  institution_ids?: string[];
  region_ids?: string[];
}

export interface UserAdmin extends User {
  registration_status: "PENDING" | "APPROVED" | "REJECTED";
  created_at: string;
  last_login_at?: string | null;
  grants: Array<{ id: string; role_key: RoleKey; role_name: string; scope_type: "GLOBAL" | "REGION" | "INSTITUTION"; institution_id?: string | null; region_id?: string | null; is_active: boolean }>;
}

export interface Institution {
  id: string;
  name: string;
  code?: string | null;
  region_id?: string | null;
  region_name?: string | null;
}

export interface Application {
  id: string;
  reference_number: string;
  institution_id: string;
  application_type: string;
  title: string;
  status: string;
  current_stage_key: string;
  workflow_template_version_id: string;
  assigned_region_id: string;
  submitted_at?: string | null;
  current_version_number: number;
  created_at: string;
  updated_at: string;
  row_version: number;
  latest_data?: Record<string, unknown>;
}

export interface ApplicationHistoryEntry {
  id: string;
  sequence: number;
  transition_key: string;
  from_stage_key?: string | null;
  to_stage_key: string;
  actor_id: string;
  comment?: string | null;
  facts: Record<string, unknown>;
  created_at: string;
}

export interface TransitionOption {
  transition_key: string;
  allowed: boolean;
  reason_code: string;
  explanation: string;
  missing_prerequisites: string[];
  required_permission?: string | null;
  applicable_workflow_version: string;
  to_stage_key?: string | null;
}

export interface DocumentRecord {
  id: string;
  institution_id: string;
  application_id?: string | null;
  classification: string;
  current_version_number: number;
  status: string;
  created_at: string;
  versions: DocumentVersion[];
}

export interface DocumentVersion {
  id: string;
  version_number: number;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  processing_status: string;
  created_at: string;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  status: string;
  created_at: string;
  read_at?: string | null;
}

export interface Deficiency {
  id: string;
  application_id: string;
  identifier: string;
  status: string;
  description: string;
  finding_id?: string | null;
  created_at: string;
  resolved_at?: string | null;
  responses?: Array<{ response_text: string; document_id?: string | null; created_at: string }>;
}

export interface ReviewerAssignment {
  id: string;
  application_id: string;
  reviewer_id: string;
  assigned_by_user_id: string;
  responsibility: string;
  status: string;
  valid_from: string;
  valid_until?: string | null;
  revoked_at?: string | null;
  reason?: string | null;
}

export interface AuditEvent {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_id?: string | null;
  actor_context?: Record<string, unknown>;
  outcome: string;
  created_at: string;
  reason?: string | null;
  correlation_id?: string | null;
}

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}

export interface EvcVisit {
  id: string;
  application_id: string;
  coordinator_id: string;
  status: string;
  scheduled_start: string;
  duration_minutes: number;
  timezone: string;
  visit_mode: string;
  location: string;
  notes?: string | null;
  row_version: number;
}

export interface EvcEvidence {
  id: string;
  visit_id: string;
  document_id: string;
  document_version_id: string;
  purpose: string;
  status: string;
  comment?: string | null;
  verified_at?: string | null;
}

export interface EvcVisitDetail {
  visit: EvcVisit;
  personnel: Array<{ id: string; user_id: string; role: string; status: string }>;
  checklist: Array<{ id: string; label: string; status: string; note?: string | null; completed_at?: string | null }>;
  reports: Array<{ id: string; status: string; summary: string; return_reason?: string | null; created_at: string }>;
  evidence: EvcEvidence[];
}

export interface ComplianceObligation { id: string; application_id: string; institution_id: string; title: string; description?: string | null; due_at?: string | null; timezone: string; required_evidence: boolean; status: string; row_version: number; }
export interface ValidityRecord { id: string; document_id: string; document_version_id: string; category: string; issuing_authority?: string | null; issue_date?: string | null; expiry_date?: string | null; advance_notice_days: number; verification_status: string; renewal_status: string; }
export interface PendencyDashboard { generated_at: string; total_active: number; by_stage: Record<string, number>; by_region: Record<string, number>; ageing: Record<string, number>; overdue: number; unassigned: number; evc_pending: number; compliance_open: number; expiring_documents: number; cases: Array<{ id: string; reference_number: string; title: string; stage: string; status: string; last_action_at: string; ageing_days: number }>; }
export interface GuidanceSource { id: string; key: string; title: string; source_type: string; issuing_organization?: string | null; source_reference?: string | null; versions: GuidanceVersion[]; }
export interface GuidanceVersion { id: string; source_id?: string; version_number: number; version_label: string; effective_date?: string | null; content_hash?: string | null; status: string; verification_status: string; reviewed_by_user_id?: string | null; reviewed_at?: string | null; }
export interface GuidanceExtractionPage { id: string; page_number: number; raw_text: string; corrected_text?: string | null; method: string; confidence?: number | null; warnings: string[]; corrected_at?: string | null; corrections?: { revision_number: number; corrected_text: string; reason: string; corrected_at: string }[]; }
export interface GuidanceExtractionRun { id: string; source_version_id: string; document_id: string; document_version_id: string; attempt_number: number; status: string; extractor_name: string; extractor_version?: string | null; failure_category?: string | null; warnings: string[]; started_at?: string | null; completed_at?: string | null; review_status: string; review_reason?: string | null; reviewed_at?: string | null; pages?: GuidanceExtractionPage[]; }
export interface CatalogueRequirement { id: string; stable_identifier: string; version_number: number; source_version_id: string; title: string; description: string; category: string; module_key: string; section_reference?: string | null; status: string; reviewed_by_user_id?: string | null; reviewed_at?: string | null; }
export interface RequirementEvidenceMapping { id: string; requirement_id: string; application_id: string; document_id: string; document_version_id: string; status: string; explanation: string; mapping_method: string; created_by_user_id: string; reviewed_by_user_id?: string | null; reviewed_at?: string | null; review_reason?: string | null; }
