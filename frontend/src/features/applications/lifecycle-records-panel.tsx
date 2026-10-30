import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type Props = {
  applicationId: string;
  stageKey: string;
  rowVersion: number;
  currentUserId?: string;
  canManageCommittee: boolean;
  canSubmitCommittee: boolean;
  canFinalizeCommittee: boolean;
  canDecide: boolean;
  canManageCommunication: boolean;
  canApproveCommunication: boolean;
};

const committeeRecommendations = ["RECOMMEND_APPROVAL", "RECOMMEND_REJECTION", "RETURN", "DEFER"];
const decisionOutcomes = ["APPROVED", "REJECTED", "RETURNED", "DEFERRED"];

export function LifecycleRecordsPanel(props: Props) {
  const cache = useQueryClient();
  const [committeeType, setCommitteeType] = useState("SYNTHETIC_PANEL");
  const [memberId, setMemberId] = useState("");
  const [findings, setFindings] = useState("");
  const [recommendation, setRecommendation] = useState("RECOMMEND_APPROVAL");
  const [finalOutcome, setFinalOutcome] = useState("RECOMMEND_APPROVAL");
  const [finalizationReason, setFinalizationReason] = useState("");
  const [decisionOutcome, setDecisionOutcome] = useState("APPROVED");
  const [decisionRationale, setDecisionRationale] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  const committees = useQuery({
    queryKey: ["application", props.applicationId, "committee-reviews"],
    queryFn: () => api.committeeReviews(props.applicationId),
  });
  const openReview = committees.data?.find((item) => item.status === "OPEN");
  const reviewDetail = useQuery({
    queryKey: ["committee-review", openReview?.id],
    queryFn: () => api.committeeReview(openReview?.id ?? ""),
    enabled: Boolean(openReview?.id),
  });
  const decisions = useQuery({ queryKey: ["application", props.applicationId, "decisions"], queryFn: () => api.decisions(props.applicationId) });
  const messages = useQuery({ queryKey: ["application", props.applicationId, "communications"], queryFn: () => api.communications(props.applicationId) });
  const command = useMutation({
    mutationFn: (operation: () => Promise<unknown>) => operation(),
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["application", props.applicationId] }),
        cache.invalidateQueries({ queryKey: ["committee-review"] }),
      ]);
    },
  });

  useEffect(() => {
    const draft = messages.data?.find((item) => item.id === editingId);
    if (draft) {
      setSubject(draft.subject);
      setBody(draft.body);
    }
  }, [editingId, messages.data]);

  const isAssignedMember = Boolean(props.currentUserId && reviewDetail.data?.members.some((member) => member.user_id === props.currentUserId && member.is_active));
  const error = command.error instanceof ApiError ? command.error.message : command.isError ? "The lifecycle operation could not be completed." : null;
  const clearComposer = () => { setEditingId(null); setSubject(""); setBody(""); };

  return <Card className="space-y-6">
    <div><h2 className="text-base font-semibold">Lifecycle records</h2><p className="text-sm text-muted">Committee outcomes and decisions are records only. A configured workflow transition is the only action that changes official application state.</p></div>
    {error ? <Alert>{error}</Alert> : null}

    <section className="border-t pt-5"><h3 className="font-medium">Committee reviews</h3>
      {committees.isLoading ? <p className="mt-2 text-sm text-muted">Loading committee reviews…</p> : null}
      {committees.data?.map((item) => <div className="mt-2 rounded border p-3 text-sm" key={item.id}><Badge tone={item.status === "FINALIZED" ? "success" : "warning"}>{item.status}</Badge><span className="ml-2">{item.committee_type} · {item.stage_key}</span><p className="mt-1 text-muted">{item.outcome ? `Advisory outcome: ${item.outcome}` : "Awaiting member findings and consolidation."}</p>{item.outcome_reason ? <p className="mt-1 text-muted">{item.outcome_reason}</p> : null}</div>)}
      {!openReview && props.canManageCommittee ? <div className="mt-3 flex flex-col gap-2 sm:flex-row"><Input value={committeeType} onChange={(event) => setCommitteeType(event.target.value)} aria-label="Committee type" /><Button disabled={command.isPending || committeeType.trim().length < 2} onClick={() => command.mutate(() => api.createCommitteeReview(props.applicationId, { stage_key: props.stageKey, committee_type: committeeType }))}>Create review</Button></div> : null}
      {openReview ? <div className="mt-3 space-y-3 rounded bg-slate-50 p-3"><p className="text-sm font-medium">Open review at {openReview.stage_key}</p>{reviewDetail.isLoading ? <p className="text-sm text-muted">Loading assigned members and submissions…</p> : null}{reviewDetail.data ? <div className="space-y-2 text-sm"><p className="text-muted">Assigned members: {reviewDetail.data.members.length}</p>{reviewDetail.data.submissions.map((submission) => <div className="rounded border bg-white p-2" key={submission.id}><p className="font-medium">{submission.recommendation}</p><p>{submission.findings}</p></div>)}{reviewDetail.data.submissions.length === 0 ? <p className="text-muted">No findings have been submitted.</p> : null}</div> : null}{props.canManageCommittee ? <div className="flex flex-col gap-2 sm:flex-row"><Input value={memberId} onChange={(event) => setMemberId(event.target.value)} placeholder="Eligible member UUID" aria-label="Eligible committee member UUID" /><Button disabled={command.isPending || !memberId.trim()} onClick={() => command.mutate(() => api.assignCommitteeMember(openReview.id, memberId))}>Assign member</Button></div> : null}{props.canSubmitCommittee && isAssignedMember ? <div className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]"><select aria-label="Committee recommendation" className="rounded-md border bg-white px-3 text-sm" value={recommendation} onChange={(event) => setRecommendation(event.target.value)}>{committeeRecommendations.map((item) => <option key={item}>{item}</option>)}</select><Input value={findings} onChange={(event) => setFindings(event.target.value)} placeholder="Findings" aria-label="Committee findings" /><Button disabled={command.isPending || findings.trim().length < 5} onClick={() => command.mutate(() => api.submitCommitteeReview(openReview.id, { recommendation, findings }))}>Submit findings</Button></div> : null}{props.canFinalizeCommittee ? <div className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]"><select aria-label="Committee outcome" className="rounded-md border bg-white px-3 text-sm" value={finalOutcome} onChange={(event) => setFinalOutcome(event.target.value)}>{committeeRecommendations.map((item) => <option key={item}>{item}</option>)}</select><Input value={finalizationReason} onChange={(event) => setFinalizationReason(event.target.value)} placeholder="Finalization reason" aria-label="Committee finalization reason" /><Button disabled={command.isPending || finalizationReason.trim().length < 5} onClick={() => command.mutate(() => api.finalizeCommitteeReview(openReview.id, { outcome: finalOutcome, reason: finalizationReason }))}>Finalize advisory outcome</Button></div> : null}</div> : null}
    </section>

    <section className="border-t pt-5"><h3 className="font-medium">Official decisions</h3>{decisions.data?.map((item) => <div className="mt-2 rounded border p-3 text-sm" key={item.id}><p className="font-medium">{item.outcome} · {item.workflow_stage_key}</p><p className="mt-1 text-muted">{item.rationale}</p></div>)}{decisions.data?.length === 0 ? <p className="mt-2 text-sm text-muted">No decision is recorded for this application.</p> : null}{props.canDecide ? <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_2fr_auto]"><select aria-label="Decision outcome" className="rounded-md border bg-white px-3 text-sm" value={decisionOutcome} onChange={(event) => setDecisionOutcome(event.target.value)}>{decisionOutcomes.map((item) => <option key={item}>{item}</option>)}</select><Input value={decisionRationale} onChange={(event) => setDecisionRationale(event.target.value)} placeholder="Decision rationale" aria-label="Decision rationale" /><Button disabled={command.isPending || decisionRationale.trim().length < 5} onClick={() => command.mutate(() => api.createDecision(props.applicationId, { outcome: decisionOutcome, rationale: decisionRationale, row_version: props.rowVersion }))}>Record decision</Button></div> : null}</section>

    <section className="border-t pt-5"><h3 className="font-medium">Communications</h3><p className="mt-1 text-sm text-muted">Queueing creates a simulated delivery only; no email or SMS provider is configured.</p>{messages.data?.map((item) => <div className="mt-2 rounded border p-3 text-sm" key={item.id}><div className="flex flex-wrap items-center gap-2"><Badge tone={item.status === "SIMULATED_DELIVERED" ? "success" : "warning"}>{item.status}</Badge><span className="font-medium">{item.subject}</span></div><p className="mt-1 whitespace-pre-wrap text-muted">{item.body}</p><div className="mt-2 flex gap-2">{item.status === "DRAFT" && props.canManageCommunication ? <Button variant="outline" disabled={command.isPending} onClick={() => setEditingId(item.id)}>Edit draft</Button> : null}{item.status === "DRAFT" && props.canApproveCommunication ? <Button disabled={command.isPending} onClick={() => command.mutate(() => api.approveCommunication(item.id))}>Queue simulated delivery</Button> : null}</div></div>)}{messages.data?.length === 0 ? <p className="mt-2 text-sm text-muted">No communication drafts exist.</p> : null}{props.canManageCommunication ? <div className="mt-3 space-y-2"><Input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject" aria-label="Communication subject" /><textarea className="min-h-20 w-full rounded border p-2 text-sm" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Message body" aria-label="Message body" />{editingId ? <div className="flex gap-2"><Button disabled={command.isPending || subject.trim().length < 2 || body.trim().length < 2} onClick={() => command.mutate(() => api.updateCommunication(editingId, { subject, body }))}>Save draft</Button><Button variant="outline" disabled={command.isPending} onClick={clearComposer}>Cancel</Button></div> : <Button disabled={command.isPending || subject.trim().length < 2 || body.trim().length < 2} onClick={() => command.mutate(() => api.createCommunication(props.applicationId, { subject, body }))}>Create draft</Button>}</div> : null}</section>
  </Card>;
}
