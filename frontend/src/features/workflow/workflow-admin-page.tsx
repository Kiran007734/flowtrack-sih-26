import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function WorkflowAdminPage() {
  const cache = useQueryClient();
  const [templateId, setTemplateId] = useState("");
  const [routeType, setRouteType] = useState("SYNTHETIC_ROUTE");
  const [configuration, setConfiguration] = useState(() => JSON.stringify({
    stages: [
      { key: "draft", display_name: "Draft", ordinal: 10, is_initial: true, entry_prerequisites: [] },
      { key: "review", display_name: "Review", ordinal: 20, is_initial: false, entry_prerequisites: [] },
    ],
    transitions: [{ key: "advance_to_review", from_stage_key: "draft", to_stage_key: "review", required_permission: "workflow.transition", authorized_role_keys: ["REGIONAL_OFFICER"], prerequisites: {}, blocking_conditions: {}, explanation: "Advance to review" }],
  }, null, 2));
  const templates = useQuery({ queryKey: ["workflow-templates"], queryFn: api.workflowTemplates });
  const command = useMutation({
    mutationFn: (operation: () => Promise<unknown>) => operation(),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["workflow-templates"] }),
  });

  useEffect(() => {
    if (!templateId && templates.data?.[0]) setTemplateId(templates.data[0].id);
  }, [templateId, templates.data]);

  let parsedConfiguration: { stages: Array<{ key: string; display_name: string; ordinal: number; is_initial: boolean; entry_prerequisites: string[] }>; transitions: Array<{ key: string; from_stage_key: string; to_stage_key: string; required_permission: string; authorized_role_keys: string[]; prerequisites: Record<string, unknown>; blocking_conditions: Record<string, unknown>; explanation: string }> } | null = null;
  try { parsedConfiguration = JSON.parse(configuration); } catch { /* surfaced below */ }
  const configurationIsValid = Boolean(parsedConfiguration && Array.isArray(parsedConfiguration.stages) && Array.isArray(parsedConfiguration.transitions));
  const error = command.error instanceof ApiError ? command.error.message : command.isError ? "Workflow operation failed." : null;
  if (templates.isLoading) return <Card>Loading workflow configurations…</Card>;
  if (templates.isError) return <Alert>Unable to load workflow configurations.</Alert>;

  return <div className="space-y-6">
    <div><h1 className="page-title">Workflow administration</h1><p className="page-description">Synthetic, versioned configuration. Publishing a new version never migrates applications already pinned to a historical version.</p></div>
    {error ? <Alert>{error}</Alert> : null}
    <Card><h2 className="font-semibold">Configured templates and version history</h2>{templates.data?.map((template) => <div className="mt-3 rounded border p-3" key={template.id}><p className="font-medium">{template.name} <span className="text-xs text-muted">{template.key}</span></p>{template.versions.map((version) => <div className="mt-2 flex flex-wrap items-center gap-2 text-sm" key={version.id}><Badge tone={version.is_published ? "success" : "warning"}>{version.is_published ? "Published" : "Draft"}</Badge><span>v{version.version_number} · {version.route_type}</span>{!version.is_published ? <Button variant="outline" disabled={command.isPending} onClick={() => { if (window.confirm("Publish this validated synthetic workflow version? Existing applications will remain pinned to their current version.")) command.mutate(() => api.publishWorkflowVersion(version.id)); }}>Publish</Button> : null}</div>)}</div>)}{templates.data?.length === 0 ? <p className="mt-3 text-sm text-muted">No workflow templates are configured.</p> : null}</Card>
    <Card><h2 className="font-semibold">Create a draft version</h2><p className="mt-1 text-sm text-muted">Define any supported stages and transitions. Stage prerequisites name earlier stage keys. Transition permissions and roles must be registered by the server; every stage must be reachable from the one initial stage. Cycles are supported when they remain reachable.</p><div className="mt-3 grid gap-2 sm:grid-cols-2"><label className="text-sm font-medium">Template<select className="mt-1 h-10 w-full rounded-md border bg-white px-3 text-sm" value={templateId} onChange={(event) => setTemplateId(event.target.value)} aria-label="Workflow template">{templates.data?.map((template) => <option value={template.id} key={template.id}>{template.name} ({template.key})</option>)}</select></label><label className="text-sm font-medium">Route type<Input className="mt-1" value={routeType} onChange={(event) => setRouteType(event.target.value)} aria-label="Route type" /></label></div><label className="mt-3 block text-sm font-medium">Stages and transitions (JSON)<textarea className="mt-1 min-h-80 w-full rounded-md border border-slate-300 p-3 font-mono text-xs" value={configuration} onChange={(event) => setConfiguration(event.target.value)} aria-label="Workflow configuration" /></label>{!configurationIsValid ? <p className="mt-2 text-sm text-red-700">Enter a JSON object with stages and transitions arrays.</p> : null}<Button className="mt-3" disabled={command.isPending || !templateId || routeType.trim().length < 2 || !configurationIsValid} onClick={() => { if (parsedConfiguration) command.mutate(() => api.createWorkflowVersion(templateId, { route_type: routeType.trim(), ...parsedConfiguration })); }}>Create draft</Button></Card>
  </div>;
}
