import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { Application } from "@/types/domain";

export function CorrectionWorkspace({ application }: { application: Application }) {
  const client = useQueryClient();
  const [responses, setResponses] = useState<Record<string, string>>({});
  const deficiencies = useQuery({ queryKey: ["application", application.id, "deficiencies"], queryFn: () => api.deficiencies(application.id) });
  const respond = useMutation({ mutationFn: ({ id, text }: { id: string; text: string }) => api.respondToDeficiency(id, { response_text: text }), onSuccess: () => void client.invalidateQueries({ queryKey: ["application", application.id, "deficiencies"] }) });
  const resubmit = useMutation({ mutationFn: () => api.transitionApplication(application.id, "resubmit_after_correction", { row_version: application.row_version, comment: "Synthetic correction package resubmitted" }), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["application", application.id] }); await client.invalidateQueries({ queryKey: ["application", application.id, "timeline"] }); } });
  if (application.status !== "RETURNED") return null;
  const unresolved = deficiencies.data?.items.filter((item) => item.status !== "RESPONDED" && item.status !== "RESOLVED") ?? [];
  const error = respond.error instanceof ApiError ? respond.error.message : resubmit.error instanceof ApiError ? resubmit.error.message : null;
  return <Card><h2 className="text-base font-semibold text-slate-900">Correction package</h2><p className="mt-1 text-sm text-muted">Deadline policy is not configured for this synthetic prototype. Earlier documents and findings remain preserved.</p>{error ? <Alert className="mt-3">{error}</Alert> : null}{deficiencies.isLoading ? <p className="mt-4 text-sm text-muted">Loading deficiencies…</p> : null}{deficiencies.data?.items.map((item) => <div key={item.id} className="mt-4 rounded-md border border-slate-200 p-4"><p className="font-mono text-xs text-muted">{item.identifier}</p><p className="mt-1 text-sm text-slate-800">{item.description}</p><p className="mt-1 text-xs text-muted">Status: {item.status}</p>{item.status !== "RESPONDED" && item.status !== "RESOLVED" ? <div className="mt-3"><label className="text-sm font-medium">Corrective response<textarea className="mt-1 min-h-20 w-full rounded-md border border-slate-300 p-2" value={responses[item.id] ?? ""} onChange={(event) => setResponses((old) => ({ ...old, [item.id]: event.target.value }))} /></label><Button className="mt-2" variant="outline" disabled={respond.isPending || (responses[item.id] ?? "").trim().length < 2} onClick={() => respond.mutate({ id: item.id, text: responses[item.id] ?? "" })}>Save response</Button></div> : <p className="mt-3 text-sm text-green-700">Response recorded. Upload any new private evidence using the document control above.</p>}</div>)}<div className="mt-5"><Button disabled={resubmit.isPending || unresolved.length > 0} onClick={() => resubmit.mutate()}>{resubmit.isPending ? "Resubmitting…" : "Resubmit correction package"}</Button>{unresolved.length > 0 ? <p className="mt-2 text-xs text-muted">Respond to all deficiencies before resubmitting.</p> : null}</div></Card>;
}
