import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";

export function ScrutinyWorkspacePage() {
  const { id } = useParams();
  const { user } = useAuth();
  const client = useQueryClient();
  const [requirement, setRequirement] = useState("SYNTHETIC-REQ-1");
  const [assessment, setAssessment] = useState<"ADEQUATE" | "INADEQUATE" | "CLARIFICATION_REQUIRED">("CLARIFICATION_REQUIRED");
  const [comment, setComment] = useState("");
  const [summary, setSummary] = useState("");
  const canReview = Boolean(user?.roles.some((role) => role === "SCRUTINY_OFFICER" || role === "REGIONAL_OFFICER" || role === "REGIONAL_ADMINISTRATOR"));
  const application = useQuery({ queryKey: ["application", id], queryFn: () => api.application(id ?? ""), enabled: Boolean(id) });
  const save = useMutation({ mutationFn: () => api.saveScrutinyReview(id ?? "", { summary, findings: [{ requirement_reference: requirement, assessment, comment, references: { source: "synthetic" } }] }), onSuccess: () => void client.invalidateQueries({ queryKey: ["application", id] }) });
  if (!id || !canReview) return <Navigate to="/access-denied" replace />;
  if (application.isLoading) return <Card>Loading scrutiny workspace…</Card>;
  if (application.isError || application.data?.current_stage_key !== "scrutiny") return <Alert>This workspace is available only for an authorized case in the scrutiny stage.</Alert>;
  const error = save.error instanceof ApiError ? save.error.message : save.isError ? "Unable to save the review." : null;
  return <div className="max-w-3xl space-y-6"><div><h1 className="page-title">Synthetic scrutiny workspace</h1><p className="page-description">Record a human review finding. This does not make an official decision.</p></div><Card><div className="space-y-4">{error ? <Alert>{error}</Alert> : null}<label className="block text-sm font-medium">Requirement reference<Input className="mt-1" value={requirement} onChange={(event) => setRequirement(event.target.value)} /></label><label className="block text-sm font-medium">Assessment<select className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3" value={assessment} onChange={(event) => setAssessment(event.target.value as typeof assessment)}><option value="ADEQUATE">Adequate</option><option value="INADEQUATE">Inadequate</option><option value="CLARIFICATION_REQUIRED">Clarification required</option></select></label><label className="block text-sm font-medium">Finding comment<textarea className="mt-1 min-h-28 w-full rounded-md border border-slate-300 p-3" value={comment} onChange={(event) => setComment(event.target.value)} /></label><label className="block text-sm font-medium">Review summary<textarea className="mt-1 min-h-24 w-full rounded-md border border-slate-300 p-3" value={summary} onChange={(event) => setSummary(event.target.value)} /></label><Button disabled={save.isPending || comment.trim().length < 2} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save scrutiny finding"}</Button></div></Card></div>;
}
