import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";

export function AuditHistoryPage() {
  const events = useQuery({ queryKey: ["audit-events"], queryFn: api.auditEvents });
  if (events.isLoading) return <Card>Loading audit history…</Card>;
  if (events.isError) return <Alert><div>Audit history could not be loaded.<Button className="ml-2" variant="outline" onClick={() => void events.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button></div></Alert>;
  return <div className="space-y-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="page-title">Audit history</h1><p className="page-description">Append-only operational events available to accounts with the global audit grant.</p></div><Button variant="outline" onClick={() => void events.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button></div>{events.data?.items.length === 0 ? <Card><p className="text-sm text-muted">No audit events are available.</p></Card> : null}<div className="space-y-3">{events.data?.items.map((event) => <Card key={event.id}><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium text-slate-900">{event.action}</p><Badge tone={event.outcome === "SUCCESS" ? "success" : event.outcome === "FAILURE" ? "warning" : "info"}>{event.outcome}</Badge></div><p className="mt-1 text-sm text-muted">{event.entity_type} · {event.entity_id}</p><p className="mt-1 text-xs text-muted">{formatDate(event.created_at)}{event.actor_id ? ` · actor ${event.actor_id}` : " · system"}{event.reason ? ` · ${event.reason}` : ""}</p></Card>)}</div></div>;
}
