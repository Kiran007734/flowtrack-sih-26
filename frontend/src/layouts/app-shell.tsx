import { Bell, BookOpenCheck, CalendarCheck, ClipboardCheck, ClipboardList, FilePlus2, History, LayoutDashboard, LayoutList, LogOut, Menu, ShieldCheck, UsersRound } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "@/features/auth/auth-context";

const items = [
  { to: "/dashboard", label: "Pendency dashboard", icon: LayoutDashboard },
  { to: "/applications", label: "Applications", icon: LayoutList },
  { to: "/evc", label: "EVC workspace", icon: CalendarCheck, evcOnly: true },
  { to: "/compliance", label: "Compliance", icon: ClipboardCheck, complianceOnly: true },
  { to: "/guidance", label: "Guidance catalogue", icon: BookOpenCheck, guidanceOnly: true },
  { to: "/workflow-admin", label: "Workflow administration", icon: ClipboardList, workflowAdminOnly: true },
  { to: "/audit-history", label: "Audit history", icon: History, auditOnly: true },
  { to: "/user-management", label: "User management", icon: UsersRound, userAdminOnly: true },
  { to: "/applications/new", label: "New application", icon: FilePlus2, applicantOnly: true },
  { to: "/notifications", label: "Notifications", icon: Bell },
];

export function AppShell() {
  const { user, logout, isBusy } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const canCreate = Boolean(user?.roles.some((role) => role === "INSTITUTION_APPLICANT" || role === "INSTITUTION_ADMINISTRATOR"));
  const canUseEvc = Boolean(user?.roles.includes("EVC_COORDINATOR"));
  const canUseCompliance = Boolean(user?.roles.some((role) => role === "COMPLIANCE_OFFICER" || role === "INSTITUTION_APPLICANT" || role === "INSTITUTION_ADMINISTRATOR"));
  const canUseGuidance = Boolean(user?.permissions.includes("guidance.read"));
  const canManageWorkflow = Boolean(user?.permissions.includes("workflow-template.manage"));
  const canReadAudit = Boolean(user?.permissions.includes("audit.read"));
  const canManageUsers = Boolean(user?.permissions.includes("user.manage"));

  const signOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen bg-canvas lg:flex">
      <aside className={cn("fixed inset-y-0 left-0 z-30 w-64 border-r bg-white p-4 transition-transform lg:static lg:translate-x-0", open ? "translate-x-0" : "-translate-x-full")} aria-label="Primary navigation">
        <div className="flex items-center gap-2 px-2 py-3 text-slate-900"><ShieldCheck className="h-6 w-6 text-primary" /><span className="font-semibold">AICTE FlowTrack</span></div>
        <nav className="mt-7 space-y-1">
          {items.filter((item) => (!item.applicantOnly || canCreate) && (!item.evcOnly || canUseEvc) && (!item.complianceOnly || canUseCompliance) && (!item.guidanceOnly || canUseGuidance) && (!item.workflowAdminOnly || canManageWorkflow) && (!item.auditOnly || canReadAudit) && (!item.userAdminOnly || canManageUsers)).map((item) => {
            const Icon = item.icon;
            return <NavLink key={item.to} to={item.to} onClick={() => setOpen(false)} className={({ isActive }) => cn("flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium", isActive ? "bg-blue-50 text-blue-800" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900")}><Icon className="h-4 w-4" />{item.label}</NavLink>;
          })}
        </nav>
        <div className="absolute inset-x-4 bottom-4 border-t pt-4">
          <p className="truncate px-2 text-sm font-medium text-slate-800">{user?.display_name}</p>
          <p className="truncate px-2 text-xs text-muted">{user?.email}</p>
          <Button variant="ghost" className="mt-2 w-full justify-start" disabled={isBusy} onClick={signOut}><LogOut className="mr-2 h-4 w-4" />Sign out</Button>
        </div>
      </aside>
      {open ? <button className="fixed inset-0 z-20 bg-slate-950/20 lg:hidden" aria-label="Close navigation" onClick={() => setOpen(false)} /> : null}
      <div className="min-w-0 flex-1">
        <header className="flex h-16 items-center gap-4 border-b bg-white px-4 sm:px-6"><Button variant="ghost" className="lg:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></Button><div className="flex-1" /><div className="hidden items-center gap-2 text-sm text-muted sm:flex"><ClipboardList className="h-4 w-4" />Human-reviewed workflow</div></header>
        <main className="mx-auto max-w-7xl p-4 sm:p-6"><Outlet /></main>
      </div>
    </div>
  );
}
