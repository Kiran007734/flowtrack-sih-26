import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function AssignmentPanel({ applicationId }: { applicationId: string }) {
  const client = useQueryClient();
  const [reviewerId, setReviewerId] = useState("");
  const assignments = useQuery({ queryKey: ["application", applicationId, "assignments"], queryFn: () => api.reviewerAssignments(applicationId) });
  const assign = useMutation({ mutationFn: () => api.assignReviewer(applicationId, { reviewer_id: reviewerId, reason: "Synthetic scrutiny assignment" }), onSuccess: () => { setReviewerId(""); void client.invalidateQueries({ queryKey: ["application", applicationId, "assignments"] }); } });
  const error = assign.error instanceof ApiError ? assign.error.message : null;
  return <Card><h2 className="text-base font-semibold text-slate-900">Reviewer assignments</h2><p className="mt-1 text-sm text-muted">Only eligible, in-scope reviewers can be assigned by the backend.</p>{error ? <Alert className="mt-3">{error}</Alert> : null}<div className="mt-3 flex flex-col gap-2 sm:flex-row"><label className="sr-only" htmlFor="reviewer-id">Reviewer UUID</label><input id="reviewer-id" className="h-10 flex-1 rounded-md border border-slate-300 px-3 text-sm" placeholder="Eligible reviewer UUID" value={reviewerId} onChange={(event) => setReviewerId(event.target.value)} /><Button disabled={assign.isPending || !reviewerId} onClick={() => assign.mutate()}>{assign.isPending ? "Assigning…" : "Assign reviewer"}</Button></div>{assignments.isLoading ? <p className="mt-3 text-sm text-muted">Loading assignment history…</p> : null}{assignments.data?.items.map((item) => <div key={item.id} className="mt-3 border-t pt-3 text-sm"><span className="font-medium">{item.status}</span><span className="ml-2 font-mono text-xs text-muted">{item.reviewer_id}</span>{item.reason ? <p className="mt-1 text-muted">{item.reason}</p> : null}</div>)}</Card>;
}
