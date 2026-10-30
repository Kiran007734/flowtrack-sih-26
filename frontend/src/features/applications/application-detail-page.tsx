import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Edit3, RefreshCw, Send } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AssignmentPanel } from "@/features/applications/assignment-panel";
import { CorrectionWorkspace } from "@/features/applications/correction-workspace";
import { DocumentUpload } from "@/features/applications/document-upload";
import { LifecycleRecordsPanel } from "@/features/applications/lifecycle-records-panel";
import { useAuth } from "@/features/auth/auth-context";
import { formatDate, statusLabel } from "@/lib/utils";

export function ApplicationDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const client = useQueryClient();
  const [transitionComment, setTransitionComment] = useState("");
  const application = useQuery({ queryKey: ["application", id], queryFn: () => api.application(id ?? ""), enabled: Boolean(id) });
  const timeline = useQuery({ queryKey: ["application", id, "timeline"], queryFn: () => api.applicationTimeline(id ?? ""), enabled: Boolean(id) });
  const transitions = useQuery({ queryKey: ["application", id, "transitions"], queryFn: () => api.transitionOptions(id ?? ""), enabled: Boolean(id) });
  const canWrite = Boolean(user?.roles.some((role) => role === "INSTITUTION_APPLICANT" || role === "INSTITUTION_ADMINISTRATOR"));
  const canReview = Boolean(user?.roles.some((role) => role === "SCRUTINY_OFFICER" || role === "REGIONAL_OFFICER" || role === "REGIONAL_ADMINISTRATOR"));
  const canAssign = Boolean(user?.permissions.includes("scrutiny.assign"));
  const assist = useQuery({ queryKey: ["application", id, "ai-assist"], queryFn: () => api.aiScrutinyAssist(id ?? ""), enabled: Boolean(id && canReview) });
  const refreshApplication = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["application", id] }),
      client.invalidateQueries({ queryKey: ["applications"] }),
    ]);
  };
  const transition = useMutation({
    mutationFn: (transitionKey: string) => api.transitionApplication(id ?? "", transitionKey, { row_version: application.data?.row_version ?? 0, comment: transitionComment.trim() || undefined }),
    onSuccess: async () => { setTransitionComment(""); await refreshApplication(); },
  });

  if (!id) return <Navigate to="/applications" replace />;
  if (application.isLoading) return <Card><p className="text-sm text-muted">Loading application…</p></Card>;
  if (application.isError || !application.data) return <Alert>Unable to load this application. It may be outside your authorized scope.</Alert>;

  const record = application.data;
  const transitionError = transition.error instanceof ApiError ? transition.error.message : transition.isError ? "The workflow transition could not be completed." : null;
  const availableTransitions = transitions.data?.items.filter((item) => item.allowed) ?? [];
  const blockedTransitions = transitions.data?.items.filter((item) => !item.allowed) ?? [];

  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex flex-wrap items-center gap-3"><h1 className="page-title">{record.title}</h1><Badge tone={record.status === "DRAFT" ? "neutral" : record.status === "SUBMITTED" ? "info" : "warning"}>{statusLabel(record.status)}</Badge></div><p className="page-description font-mono">{record.reference_number} · Synthetic prototype record</p></div><div className="flex gap-2">{record.status === "DRAFT" && canWrite ? <Button variant="outline" asChild><Link to={`/applications/${record.id}/edit`}><Edit3 className="mr-2 h-4 w-4" />Edit</Link></Button> : null}{record.current_stage_key === "scrutiny" && canReview ? <Button variant="outline" asChild><Link to={`/applications/${record.id}/scrutiny`}>Scrutiny workspace</Link></Button> : null}{record.status === "DRAFT" && availableTransitions.some((item) => item.transition_key === "submit") ? <Button disabled={transition.isPending} onClick={() => transition.mutate("submit")}><Send className="mr-2 h-4 w-4" />{transition.isPending ? "Submitting…" : "Submit"}</Button> : null}</div></div>
    {transitionError ? <Alert>{transitionError}</Alert> : null}
    <div className="grid gap-6 lg:grid-cols-3"><Card className="lg:col-span-2"><h2 className="text-base font-semibold text-slate-900">Application details</h2><dl className="mt-4 grid gap-4 sm:grid-cols-2"><div><dt className="text-xs font-medium uppercase tracking-wide text-muted">Category</dt><dd className="mt-1 text-sm text-slate-800">{statusLabel(record.application_type)}</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted">Current stage</dt><dd className="mt-1 text-sm text-slate-800">{statusLabel(record.current_stage_key)}</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted">Submitted</dt><dd className="mt-1 text-sm text-slate-800">{formatDate(record.submitted_at)}</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted">Last updated</dt><dd className="mt-1 text-sm text-slate-800">{formatDate(record.updated_at)}</dd></div></dl></Card><Card><h2 className="text-base font-semibold text-slate-900">Workflow safety</h2><p className="mt-2 text-sm text-muted">Stage changes are evaluated by the backend against the bound synthetic workflow version. AI cannot change this state.</p></Card></div>
    <Card><h2 className="text-base font-semibold text-slate-900">Authorized workflow actions</h2><p className="mt-1 text-sm text-muted">Only actions marked available were authorized by the server for the current workflow version and application state.</p>{transitions.isLoading ? <p className="mt-3 text-sm text-muted">Evaluating workflow actions…</p> : null}{availableTransitions.length > 0 ? <><Input className="mt-3" value={transitionComment} onChange={(event) => setTransitionComment(event.target.value)} placeholder="Optional transition comment" aria-label="Workflow transition comment" /> <div className="mt-3 flex flex-wrap gap-2">{availableTransitions.map((item) => <Button key={item.transition_key} disabled={transition.isPending} onClick={() => transition.mutate(item.transition_key)}>{statusLabel(item.transition_key)} → {item.to_stage_key ? statusLabel(item.to_stage_key) : "next stage"}</Button>)}</div></> : <p className="mt-3 text-sm text-muted">No workflow action is currently available to this account.</p>}{blockedTransitions.length > 0 ? <details className="mt-4 text-sm"><summary className="cursor-pointer font-medium">Why other transitions are unavailable</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-muted">{blockedTransitions.map((item) => <li key={item.transition_key}>{statusLabel(item.transition_key)}: {item.explanation}{item.missing_prerequisites.length ? ` (${item.missing_prerequisites.join("; ")})` : ""}</li>)}</ul></details> : null}</Card>
    <DocumentUpload applicationId={record.id} canUpload={canWrite && record.status === "DRAFT"} />
    {canWrite ? <CorrectionWorkspace application={record} /> : null}
    {canAssign ? <AssignmentPanel applicationId={record.id} /> : null}
    <LifecycleRecordsPanel applicationId={record.id} stageKey={record.current_stage_key} rowVersion={record.row_version} currentUserId={user?.id} canManageCommittee={Boolean(user?.permissions.includes("committee.manage"))} canSubmitCommittee={Boolean(user?.permissions.includes("committee.review"))} canFinalizeCommittee={Boolean(user?.permissions.includes("committee.finalize"))} canDecide={Boolean(user?.permissions.includes("decision.record"))} canManageCommunication={Boolean(user?.permissions.includes("communication.manage"))} canApproveCommunication={Boolean(user?.permissions.includes("communication.approve"))} />
    {canReview ? <Card><h2 className="text-base font-semibold text-slate-900">Grounded review assistance</h2><p className="mt-1 text-sm text-muted">Non-binding, read-only assistance. Human reviewers retain all decision authority.</p>{assist.isLoading ? <p className="mt-3 text-sm text-muted">Checking accessible sources…</p> : null}{assist.isError ? <Alert>Assistance could not be loaded. Continue with normal human review.</Alert> : null}{assist.data ? <div className="mt-3 space-y-3 text-sm"><Alert>{assist.data.corpus_status}</Alert><div><p className="font-medium">Source-backed facts</p><p className="text-muted">Submitted versions: {assist.data.source_backed_facts.submitted_document_count}; compliance evidence records: {assist.data.source_backed_facts.compliance_evidence_count}</p>{assist.data.sources.map((source) => <p className="text-xs text-muted" key={source.document_version_id}>{source.filename} · version {source.document_version_id} · {source.source_kind}</p>)}</div><div><p className="font-medium">Human-review suggestions</p><ul className="list-disc pl-5 text-muted">{assist.data.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul></div><div><p className="font-medium">Limitations</p><ul className="list-disc pl-5 text-muted">{assist.data.uncertainty.map((item) => <li key={item}>{item}</li>)}</ul></div></div> : null}</Card> : null}
    <Card><div className="flex items-center justify-between"><div><h2 className="text-base font-semibold text-slate-900">Stage history</h2><p className="mt-1 text-sm text-muted">Append-only application transition record.</p></div><Button variant="ghost" aria-label="Refresh history" onClick={() => void timeline.refetch()}><RefreshCw className="h-4 w-4" /></Button></div>{timeline.isLoading ? <p className="mt-4 text-sm text-muted">Loading timeline…</p> : null}{timeline.data?.items.length === 0 ? <p className="mt-4 text-sm text-muted">No history is available.</p> : null}<ol className="mt-5 space-y-4 border-l border-slate-200 pl-5">{timeline.data?.items.map((item) => <li key={item.id} className="relative"><CheckCircle2 className="absolute -left-[31px] top-0 h-4 w-4 bg-white text-blue-600" /><p className="text-sm font-medium text-slate-800">{statusLabel(item.transition_key)}</p><p className="mt-0.5 text-sm text-muted">{item.from_stage_key ? `${statusLabel(item.from_stage_key)} → ` : ""}{statusLabel(item.to_stage_key)} · {formatDate(item.created_at)}</p>{item.comment ? <p className="mt-1 text-sm text-slate-600">{item.comment}</p> : null}</li>)}</ol></Card>
  </div>;
}
