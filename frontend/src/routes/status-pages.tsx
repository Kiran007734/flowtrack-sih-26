import { ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function AccessDeniedPage() {
  return <main className="flex min-h-screen items-center justify-center bg-canvas p-6"><Card className="max-w-md text-center"><ShieldAlert className="mx-auto h-10 w-10 text-amber-600" /><h1 className="mt-4 text-xl font-semibold text-slate-900">Access denied</h1><p className="mt-2 text-sm text-muted">Your current role and scope do not allow this action.</p><Button className="mt-5" asChild><Link to="/applications">Return to applications</Link></Button></Card></main>;
}

export function NotFoundPage() {
  return <main className="flex min-h-screen items-center justify-center bg-canvas p-6"><Card className="max-w-md text-center"><h1 className="text-xl font-semibold text-slate-900">Page not found</h1><p className="mt-2 text-sm text-muted">The page you requested does not exist or is no longer available.</p><Button className="mt-5" asChild><Link to="/applications">Return to applications</Link></Button></Card></main>;
}
