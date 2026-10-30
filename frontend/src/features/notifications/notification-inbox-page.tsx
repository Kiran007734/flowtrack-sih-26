import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, RefreshCw } from "lucide-react";
import { api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";

export function NotificationInboxPage() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["notifications"], queryFn: api.notifications });
  const markRead = useMutation({ mutationFn: api.markNotificationRead, onSuccess: () => void client.invalidateQueries({ queryKey: ["notifications"] }) });
  return <div className="space-y-6"><div><h1 className="page-title">Notifications</h1><p className="page-description">Durable in-app notifications created from processed outbox events.</p></div>{query.isLoading ? <Card><p className="text-sm text-muted">Loading notifications…</p></Card> : null}{query.isError ? <Alert><div><p>Unable to load notifications.</p><Button className="mt-2" variant="outline" onClick={() => void query.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Try again</Button></div></Alert> : null}{query.data?.items.length === 0 ? <Card><div className="flex items-center gap-3 text-muted"><Bell className="h-5 w-5" /><p className="text-sm">No notifications yet.</p></div></Card> : null}<div className="space-y-3">{query.data?.items.map((item) => <Card key={item.id} className={item.status === "UNREAD" ? "border-blue-200" : ""}><div className="flex gap-4"><Bell className="mt-0.5 h-5 w-5 shrink-0 text-primary" /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-medium text-slate-900">{item.title}</h2><Badge tone={item.status === "UNREAD" ? "info" : "neutral"}>{item.status === "UNREAD" ? "Unread" : "Read"}</Badge></div><p className="mt-1 text-sm text-slate-600">{item.body}</p><p className="mt-2 text-xs text-muted">{formatDate(item.created_at)}</p></div>{item.status === "UNREAD" ? <Button variant="ghost" disabled={markRead.isPending} onClick={() => markRead.mutate(item.id)}><CheckCheck className="mr-2 h-4 w-4" />Mark read</Button> : null}</div></Card>)}</div></div>;
}
