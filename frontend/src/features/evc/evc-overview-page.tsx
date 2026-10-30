import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/api/client";

export function EvcOverviewPage() {
  const query = useQuery({ queryKey: ["evc-visits"], queryFn: () => api.evcVisits() });
  const visits = query.data ?? [];
  const count = (statuses: string[]) => visits.filter((visit) => statuses.includes(visit.status)).length;
  if (query.isLoading) return <Card><p className="text-sm text-muted">Loading EVC workspace…</p></Card>;
  if (query.isError) return <Alert><div>Unable to load EVC visits.<Button className="ml-2" variant="outline" onClick={() => void query.refetch()}>Retry</Button></div></Alert>;
  return <div className="space-y-6"><div className="flex items-center justify-between"><div><h1 className="page-title">EVC workspace</h1><p className="page-description">Authorized synthetic visit coordination and evidence review.</p></div><Button asChild><Link to="/evc/visits">View visits</Link></Button></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["Upcoming", count(["CONFIRMED"])], ["In progress", count(["IN_PROGRESS"])], ["Completed", count(["COMPLETED"])], ["Cancelled", count(["CANCELLED"])]].map(([label, value]) => <Card key={String(label)}><p className="text-sm text-muted">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></Card>)}</div><Card><h2 className="font-semibold">Outstanding visits</h2><div className="mt-3 space-y-2">{visits.filter((visit) => !["COMPLETED", "CANCELLED"].includes(visit.status)).map((visit) => <Link key={visit.id} className="flex items-center justify-between rounded border p-3 hover:bg-slate-50" to={`/evc/visits/${visit.id}`}><span className="text-sm font-medium">{visit.location}</span><span className="flex items-center gap-3 text-sm text-muted">{new Date(visit.scheduled_start).toLocaleString()}<Badge tone="info">{visit.status}</Badge></span></Link>)}{visits.length === 0 ? <p className="text-sm text-muted">No EVC visits are available in your authorized scope.</p> : null}</div></Card></div>;
}
