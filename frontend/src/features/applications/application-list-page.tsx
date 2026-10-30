import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, FilePlus2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";
import { formatDate, statusLabel } from "@/lib/utils";

function applicationTone(status: string): "neutral" | "success" | "warning" | "info" {
  if (status === "ROUTE_COMPLETE") return "success";
  if (status === "DRAFT") return "neutral";
  if (status === "SUBMITTED") return "info";
  return "warning";
}

export function ApplicationListPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [cursorStack, setCursorStack] = useState<string[]>([]);
  const filters = {
    search: params.get("search") ?? "",
    institution_id: params.get("institution_id") ?? "",
    status: params.get("status") ?? "",
    stage: params.get("stage") ?? "",
    created_from: params.get("created_from") ?? "",
    created_to: params.get("created_to") ?? "",
    sort_by: params.get("sort_by") ?? "created_at",
    sort_direction: (params.get("sort_direction") === "asc" ? "asc" : "desc") as "asc" | "desc",
    cursor: cursorStack.at(-1) ?? "",
    limit: 25,
  };
  const query = useQuery({ queryKey: ["applications", filters], queryFn: () => api.applications(filters) });
  const institutions = useQuery({ queryKey: ["institutions", "application-filter"], queryFn: api.institutions });
  const canCreate = Boolean(user?.roles.some((role) => role === "INSTITUTION_APPLICANT" || role === "INSTITUTION_ADMINISTRATOR"));
  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setCursorStack([]);
    setParams(next, { replace: true });
  };
  const resetFilters = () => { setCursorStack([]); setParams({}, { replace: true }); };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="page-title">Applications</h1><p className="page-description">Only records within your authorized institution or regional scope are shown.</p></div>
        {canCreate ? <Button asChild><Link to="/applications/new"><FilePlus2 className="mr-2 h-4 w-4" />New application</Link></Button> : null}
      </div>
      <Card className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm font-medium">Search reference or title<Input className="mt-1" value={filters.search} onChange={(event) => setFilter("search", event.target.value)} placeholder="Search applications" /></label>
          <label className="text-sm font-medium">Status<select className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" value={filters.status} onChange={(event) => setFilter("status", event.target.value)}><option value="">All statuses</option><option value="DRAFT">Draft</option><option value="SUBMITTED">Submitted</option><option value="IN_REVIEW">In review</option><option value="RETURNED">Returned</option><option value="ROUTE_COMPLETE">Complete</option></select></label>
          <label className="text-sm font-medium">Institution<select className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" value={filters.institution_id} onChange={(event) => setFilter("institution_id", event.target.value)} disabled={institutions.isLoading}><option value="">All authorized institutions</option>{institutions.data?.items.map((institution) => <option key={institution.id} value={institution.id}>{institution.name}</option>)}</select></label>
          <label className="text-sm font-medium">Stage<Input className="mt-1" value={filters.stage} onChange={(event) => setFilter("stage", event.target.value)} placeholder="For example: scrutiny" /></label>
          <label className="text-sm font-medium">Sort<select className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" value={`${filters.sort_by}:${filters.sort_direction}`} onChange={(event) => { const [sort_by, sort_direction] = event.target.value.split(":"); const next = new URLSearchParams(params); next.set("sort_by", sort_by); next.set("sort_direction", sort_direction); setCursorStack([]); setParams(next, { replace: true }); }}><option value="created_at:desc">Newest created</option><option value="created_at:asc">Oldest created</option><option value="updated_at:desc">Recently updated</option><option value="title:asc">Title A–Z</option><option value="reference_number:asc">Reference A–Z</option></select></label>
          <label className="text-sm font-medium">Created from<Input className="mt-1" type="date" value={filters.created_from} onChange={(event) => setFilter("created_from", event.target.value)} /></label>
          <label className="text-sm font-medium">Created to<Input className="mt-1" type="date" value={filters.created_to} onChange={(event) => setFilter("created_to", event.target.value)} /></label>
        </div>
        <Button variant="outline" onClick={resetFilters}>Reset filters</Button>
      </Card>
      {query.isLoading ? <Card><p className="text-sm text-muted">Loading applications…</p></Card> : null}
      {query.isError ? <Alert><div><p>Unable to load applications.</p><Button className="mt-2" variant="outline" onClick={() => void query.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Try again</Button></div></Alert> : null}
      {query.data && query.data.items.length === 0 ? <Card><h2 className="font-medium text-slate-900">No applications available</h2><p className="mt-1 text-sm text-muted">Create a draft if your role has institution applicant access.</p></Card> : null}
      {query.data && query.data.items.length > 0 ? <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto"><table className="min-w-full divide-y divide-slate-200 text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Reference</th><th className="px-5 py-3">Application</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Stage</th><th className="px-5 py-3">Updated</th><th className="px-5 py-3"><span className="sr-only">Open</span></th></tr></thead><tbody className="divide-y divide-slate-100 bg-white">
          {query.data.items.map((application) => <tr key={application.id} className="hover:bg-slate-50"><td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-slate-700">{application.reference_number}</td><td className="px-5 py-4"><p className="font-medium text-slate-900">{application.title}</p><p className="mt-0.5 text-xs text-muted">{statusLabel(application.application_type)}</p></td><td className="px-5 py-4"><Badge tone={applicationTone(application.status)}>{statusLabel(application.status)}</Badge></td><td className="px-5 py-4 text-slate-600">{statusLabel(application.current_stage_key)}</td><td className="whitespace-nowrap px-5 py-4 text-slate-500">{formatDate(application.updated_at)}</td><td className="px-5 py-4 text-right"><Link className="inline-flex items-center text-sm font-medium text-primary hover:text-blue-800" to={`/applications/${application.id}`}>Open<ArrowRight className="ml-1 h-4 w-4" /></Link></td></tr>)}
        </tbody></table></div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-100 p-3"><Button variant="outline" disabled={cursorStack.length === 0 || query.isFetching} onClick={() => setCursorStack((items) => items.slice(0, -1))}><ArrowLeft className="mr-1 h-4 w-4" />Previous</Button><Button variant="outline" disabled={!query.data.next_cursor || query.isFetching} onClick={() => { if (query.data?.next_cursor) setCursorStack((items) => [...items, query.data.next_cursor!]); }}>Next<ArrowRight className="ml-1 h-4 w-4" /></Button></div>
      </Card> : null}
    </div>
  );
}
