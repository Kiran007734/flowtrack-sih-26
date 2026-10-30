import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/api/client";

export function EvcVisitListPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const search = params.get("q") ?? "";
  const query = useQuery({ queryKey: ["evc-visits", status], queryFn: () => api.evcVisits({ status: status || undefined }) });
  const visits = (query.data ?? []).filter((item) => `${item.location} ${item.application_id}`.toLowerCase().includes(search.toLowerCase()));
  const setStatus = (value: string) => {
    if (value) params.set("status", value); else params.delete("status");
    setParams(params);
  };
  return <div className="space-y-6"><div><h1 className="page-title">EVC visits</h1><p className="page-description">Results are restricted to your authorized institution and region scope.</p></div><div className="flex flex-wrap gap-3"><Input aria-label="Search EVC visits" value={search} onChange={(e) => { params.set("q", e.target.value); setParams(params); }} placeholder="Search location or application ID" /><select aria-label="Visit status" className="rounded-md border px-3 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{["PROPOSED", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED"].map((item) => <option key={item}>{item}</option>)}</select></div>{query.isLoading ? <Card>Loading visits…</Card> : null}{query.isError ? <Alert><div>Unable to load visits.<Button className="ml-2" variant="outline" onClick={() => void query.refetch()}>Retry</Button></div></Alert> : null}<div className="space-y-3">{visits.map((visit) => <Card key={visit.id}><div className="flex flex-wrap items-center justify-between gap-3"><div><Link className="font-medium text-primary hover:underline" to={`/evc/visits/${visit.id}`}>{visit.location}</Link><p className="text-sm text-muted">{new Date(visit.scheduled_start).toLocaleString()} · {visit.timezone}</p></div><Badge tone="info">{visit.status}</Badge></div></Card>)}{!query.isLoading && visits.length === 0 ? <Card><p className="text-sm text-muted">No matching EVC visits.</p></Card> : null}</div></div>;
}
