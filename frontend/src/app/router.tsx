import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApplicationDetailPage } from "@/features/applications/application-detail-page";
import { ApplicationFormPage } from "@/features/applications/application-form-page";
import { ApplicationListPage } from "@/features/applications/application-list-page";
import { ScrutinyWorkspacePage } from "@/features/applications/scrutiny-workspace-page";
import { LoginPage } from "@/features/auth/login-page";
import { SignUpPage } from "@/features/auth/sign-up-page";
import { NotificationInboxPage } from "@/features/notifications/notification-inbox-page";
import { EvcOverviewPage } from "@/features/evc/evc-overview-page";
import { EvcVisitListPage } from "@/features/evc/evc-visit-list-page";
import { EvcVisitDetailPage } from "@/features/evc/evc-visit-detail-page";
import { ComplianceWorkspacePage } from "@/features/compliance/compliance-workspace-page";
import { PendencyDashboardPage } from "@/features/dashboard/pendency-dashboard-page";
import { GuidanceWorkspacePage } from "@/features/catalogue/guidance-workspace-page";
import { WorkflowAdminPage } from "@/features/workflow/workflow-admin-page";
import { AuditHistoryPage } from "@/features/audit/audit-history-page";
import { UserManagementPage } from "@/features/admin/user-management-page";
import { AppShell } from "@/layouts/app-shell";
import { RequireAuth } from "@/routes/require-auth";
import { AccessDeniedPage, NotFoundPage } from "@/routes/status-pages";

export function AppRouter() {
  return <BrowserRouter><Routes><Route path="/login" element={<LoginPage />} /><Route path="/signup" element={<SignUpPage />} /><Route path="/access-denied" element={<AccessDeniedPage />} /><Route element={<RequireAuth><AppShell /></RequireAuth>}><Route path="/" element={<Navigate to="/applications" replace />} /><Route path="/applications" element={<ApplicationListPage />} /><Route path="/applications/new" element={<ApplicationFormPage />} /><Route path="/applications/:id" element={<ApplicationDetailPage />} /><Route path="/applications/:id/edit" element={<ApplicationFormPage />} /><Route path="/applications/:id/scrutiny" element={<ScrutinyWorkspacePage />} /><Route path="/dashboard" element={<PendencyDashboardPage />} /><Route path="/evc" element={<EvcOverviewPage />} /><Route path="/evc/visits" element={<EvcVisitListPage />} /><Route path="/evc/visits/:id" element={<EvcVisitDetailPage />} /><Route path="/compliance" element={<ComplianceWorkspacePage />} /><Route path="/guidance" element={<GuidanceWorkspacePage />} /><Route path="/workflow-admin" element={<WorkflowAdminPage />} /><Route path="/audit-history" element={<AuditHistoryPage />} /><Route path="/user-management" element={<UserManagementPage />} /><Route path="/notifications" element={<NotificationInboxPage />} /></Route><Route path="*" element={<NotFoundPage />} /></Routes></BrowserRouter>;
}
