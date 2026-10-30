import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";
import type { RoleKey, UserAdmin } from "@/types/domain";

const roles: Array<{ key: RoleKey; scope: "INSTITUTION" | "REGION" | "GLOBAL" }> = [
  { key: "INSTITUTION_APPLICANT", scope: "INSTITUTION" }, { key: "INSTITUTION_ADMINISTRATOR", scope: "INSTITUTION" },
  { key: "SCRUTINY_OFFICER", scope: "REGION" }, { key: "REGIONAL_OFFICER", scope: "REGION" }, { key: "REGIONAL_ADMINISTRATOR", scope: "REGION" },
  { key: "EVC_MEMBER", scope: "REGION" }, { key: "EVC_COORDINATOR", scope: "REGION" }, { key: "AUTHORIZED_REVIEWER", scope: "REGION" }, { key: "COMPLIANCE_OFFICER", scope: "REGION" },
  { key: "READ_ONLY_AUDITOR", scope: "GLOBAL" },
];

function errorText(error: unknown) { return error instanceof ApiError ? error.message : "The user operation could not be completed."; }

export function UserManagementPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [status, setStatus] = useState("PENDING");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<UserAdmin | null>(null);
  const [roleKey, setRoleKey] = useState<RoleKey>("INSTITUTION_APPLICANT");
  const [scopeId, setScopeId] = useState("");
  const [reason, setReason] = useState("");
  const canManageUsers = Boolean(user?.permissions.includes("user.manage"));
  const users = useQuery({ queryKey: ["users", status, query], queryFn: () => api.users(status || undefined, query || undefined), enabled: canManageUsers });
  const scopes = useQuery({ queryKey: ["user-administration-scopes"], queryFn: api.userAdministrationScopes, enabled: canManageUsers });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["users"] }); };
  const mutation = useMutation({ mutationFn: async (operation: () => Promise<unknown>) => operation(), onSuccess: async () => { await refresh(); if (selected) { const refreshed = await api.users(status || undefined, query || undefined); setSelected(refreshed.find((item) => item.id === selected.id) ?? null); } } });
  if (!canManageUsers) return <Navigate to="/access-denied" replace />;
  const scope = roles.find((item) => item.key === roleKey)?.scope ?? "INSTITUTION";
  const roleInput = () => ({ role_key: roleKey, scope_type: scope, ...(scope === "INSTITUTION" ? { institution_id: scopeId } : scope === "REGION" ? { region_id: scopeId } : {}) });
  const choose = (item: UserAdmin) => { setSelected(item); setReason(""); setScopeId(""); };
  const roleOptions = scopes.data?.regions ?? [];
  return <div className="space-y-6"><div><h1 className="page-title">User management</h1><p className="page-description">Approve account requests and manage only persisted, least-privilege role grants.</p></div>{mutation.isError ? <Alert>{errorText(mutation.error)}</Alert> : null}<Card><div className="flex flex-wrap gap-3"><select aria-label="Registration status" className="rounded border px-3" value={status} onChange={(event) => setStatus(event.target.value)}><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="">All users</option></select><Input aria-label="Search users" className="max-w-xs" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search email or name" /></div>{users.isLoading ? <p className="mt-4 text-sm text-muted">Loading users…</p> : null}{users.isError ? <Alert className="mt-4">Unable to load users. <Button variant="outline" onClick={() => void users.refetch()}>Retry</Button></Alert> : null}{users.data?.length === 0 ? <p className="mt-4 text-sm text-muted">No matching users.</p> : null}<div className="mt-4 overflow-x-auto"><table className="min-w-full text-sm"><thead><tr className="text-left text-muted"><th className="p-2">User</th><th className="p-2">Request</th><th className="p-2">Account</th><th className="p-2" /></tr></thead><tbody>{users.data?.map((item) => <tr key={item.id} className="border-t"><td className="p-2"><strong>{item.display_name}</strong><br />{item.email}</td><td className="p-2"><Badge tone={item.registration_status === "PENDING" ? "warning" : item.registration_status === "APPROVED" ? "success" : "neutral"}>{item.registration_status}</Badge></td><td className="p-2">{item.is_active ? "Active" : "Inactive"}</td><td className="p-2"><Button variant="outline" onClick={() => choose(item)}>Manage</Button></td></tr>)}</tbody></table></div></Card>{selected ? <Card><div className="flex justify-between gap-3"><div><h2 className="font-semibold">{selected.display_name}</h2><p className="text-sm text-muted">{selected.email}</p></div><Button variant="outline" onClick={() => setSelected(null)}>Close</Button></div><div className="mt-4 grid gap-3 md:grid-cols-2"><label className="text-sm">Role<select className="mt-1 w-full rounded border p-2" value={roleKey} onChange={(event) => { setRoleKey(event.target.value as RoleKey); setScopeId(""); }}>{roles.map((item) => <option key={item.key} value={item.key}>{item.key}</option>)}</select></label>{scope !== "GLOBAL" ? <label className="text-sm">{scope === "REGION" ? "Region" : "Institution"}<select className="mt-1 w-full rounded border p-2" value={scopeId} onChange={(event) => setScopeId(event.target.value)}><option value="">Select scope</option>{scope === "INSTITUTION" ? scopes.data?.institutions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>) : roleOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}</div>{selected.registration_status === "PENDING" ? <div className="mt-4 flex flex-wrap gap-2"><Button disabled={mutation.isPending || (scope !== "GLOBAL" && !scopeId)} onClick={() => mutation.mutate(() => api.approveUser(selected.id, roleInput()))}>Approve request</Button><Input aria-label="Rejection reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Rejection reason" /><Button variant="outline" disabled={mutation.isPending || reason.trim().length < 3} onClick={() => mutation.mutate(() => api.rejectUser(selected.id, reason))}>Reject request</Button></div> : <div className="mt-4 flex flex-wrap gap-2"><Button disabled={mutation.isPending} onClick={() => mutation.mutate(() => api.setUserActivation(selected.id, !selected.is_active))}>{selected.is_active ? "Deactivate account" : "Activate account"}</Button><Button disabled={mutation.isPending || (scope !== "GLOBAL" && !scopeId)} onClick={() => mutation.mutate(() => api.assignUserRole(selected.id, roleInput()))}>Assign role</Button></div>}<div className="mt-5"><h3 className="font-medium">Role grants</h3>{selected.grants.map((grant) => <div key={grant.id} className="mt-2 flex items-center justify-between rounded border p-2 text-sm"><span>{grant.role_name} · {grant.scope_type} · {grant.is_active ? "Active" : "Revoked"}</span>{grant.is_active ? <Button variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate(() => api.revokeUserRole(selected.id, grant.id))}>Revoke</Button> : null}</div>)}</div></Card> : null}</div>;
}
