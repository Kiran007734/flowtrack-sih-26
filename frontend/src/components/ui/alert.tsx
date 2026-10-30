import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export function Alert({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div role="alert" className={cn("flex gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800", className)}><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{children}</div>;
}
