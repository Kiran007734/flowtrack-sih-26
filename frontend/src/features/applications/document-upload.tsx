import { useMutation } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { DocumentRecord } from "@/types/domain";

export function DocumentUpload({ applicationId, canUpload }: { applicationId: string; canUpload: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [document, setDocument] = useState<DocumentRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (file: File) => api.uploadDocument({ applicationId, file, classification: "INTERNAL" }),
    onSuccess: (saved) => { setDocument(saved); setError(null); },
    onError: (caught) => setError(caught instanceof ApiError ? caught.message : "Unable to upload the document."),
  });
  const download = async () => {
    if (!document) return;
    const blob = await api.downloadDocument(document.id);
    const url = URL.createObjectURL(blob);
    const anchor = window.document.createElement("a");
    anchor.href = url;
    anchor.download = document.versions[0]?.original_filename ?? "document";
    anchor.click();
    URL.revokeObjectURL(url);
  };
  if (!canUpload) return null;
  return <section className="rounded-md border border-dashed border-slate-300 bg-slate-50 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-medium text-slate-800">Supporting document</h3><p className="mt-1 text-sm text-muted">PDF, PNG, or JPEG; private and access-checked.</p></div><input ref={input} className="sr-only" type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setError(null); mutation.mutate(file); } event.currentTarget.value = ""; }} /><Button variant="outline" disabled={mutation.isPending} onClick={() => input.current?.click()}><Upload className="mr-2 h-4 w-4" />{mutation.isPending ? "Uploading…" : "Upload"}</Button></div>{error ? <Alert className="mt-3">{error}</Alert> : null}{document ? <div className="mt-3 flex items-center justify-between rounded bg-white p-3 text-sm"><span className="truncate text-slate-700">{document.versions[0]?.original_filename ?? "Uploaded document"}</span><Button variant="ghost" onClick={() => void download()}><Download className="mr-2 h-4 w-4" />Download</Button></div> : null}</section>;
}
