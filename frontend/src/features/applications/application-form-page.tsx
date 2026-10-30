import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";

const schema = z.object({
  institution_id: z.string().uuid("Choose an institution."),
  application_type: z.string().trim().min(2, "Enter an application category."),
  title: z.string().trim().min(2, "Enter a title."),
  workflow_template_key: z.enum(["SCRUTINY_ONLY", "SCRUTINY_THEN_EVC", "EVC_THEN_SAC_SHC", "SCRUTINY_EVC_SAC_SHC"]),
  data_json: z.string().refine((value) => { try { const parsed: unknown = JSON.parse(value || "{}"); return Boolean(parsed) && typeof parsed === "object" && !Array.isArray(parsed); } catch { return false; } }, "Additional details must be a JSON object."),
});
type Values = z.infer<typeof schema>;

export function ApplicationFormPage() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const { user } = useAuth();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const canWrite = Boolean(user?.roles.some((role) => role === "INSTITUTION_APPLICANT" || role === "INSTITUTION_ADMINISTRATOR"));
  const institutions = useQuery({ queryKey: ["institutions"], queryFn: api.institutions, enabled: canWrite });
  const application = useQuery({ queryKey: ["application", id], queryFn: () => api.application(id ?? ""), enabled: isEdit && Boolean(id) });
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { institution_id: "", application_type: "SYNTHETIC_NEW_PROGRAMME", title: "", workflow_template_key: "SCRUTINY_ONLY", data_json: "{}" } });

  useEffect(() => {
    if (application.data) {
      form.reset({
        institution_id: application.data.institution_id,
        application_type: application.data.application_type,
        title: application.data.title,
        workflow_template_key: "SCRUTINY_ONLY",
        data_json: JSON.stringify(application.data.latest_data ?? {}, null, 2),
      });
    }
  }, [application.data, form]);

  const mutation = useMutation({
    mutationFn: async (values: Values) => {
      const data = JSON.parse(values.data_json || "{}") as Record<string, unknown>;
      return isEdit && id
        ? api.updateApplication(id, { application_type: values.application_type, title: values.title, data, row_version: application.data?.row_version ?? 0 })
        : api.createApplication({ institution_id: values.institution_id, application_type: values.application_type, title: values.title, workflow_template_key: values.workflow_template_key, data });
    },
    onSuccess: async (saved) => {
      await client.invalidateQueries({ queryKey: ["applications"] });
      await client.invalidateQueries({ queryKey: ["application", saved.id] });
      navigate(`/applications/${saved.id}`);
    },
    onError: (caught) => {
      if (caught instanceof ApiError) {
        Object.entries(caught.fieldErrors ?? {}).forEach(([field, messages]) => {
          const fieldName = field === "data" ? "data_json" : field;
          if (fieldName in form.getValues()) form.setError(fieldName as keyof Values, { message: messages.join(" ") });
        });
        setError(caught.code === "stale_row_version" ? "This draft changed elsewhere. Reload it before saving so nothing is overwritten." : caught.message);
      } else setError("Unable to save the application.");
    },
  });

  if (!canWrite) return <Navigate to="/access-denied" replace />;
  if (application.isError) return <Alert>Unable to load this application for editing.</Alert>;
  if (isEdit && application.data && application.data.status !== "DRAFT") return <Navigate to={`/applications/${id}`} replace />;

  return <div className="max-w-3xl space-y-6"><div><h1 className="page-title">{isEdit ? "Edit draft application" : "New application"}</h1><p className="page-description">All route choices are labelled synthetic prototype configurations.</p></div><Card>
    <form className="space-y-5" noValidate onSubmit={form.handleSubmit((values) => { setError(null); mutation.mutate(values); })}>
      {error ? <Alert><div>{error}{(error.includes("changed elsewhere")) ? <Button className="mt-2" variant="outline" onClick={() => void application.refetch()}>Reload saved draft</Button> : null}</div></Alert> : null}
      {institutions.isError ? <Alert>Institutions could not be loaded. You cannot choose an institution until this is resolved.</Alert> : null}
      <label className="block text-sm font-medium text-slate-700">Institution <span className="text-red-600">*</span>
        <select disabled={isEdit || institutions.isLoading} className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm disabled:bg-slate-100" aria-invalid={Boolean(form.formState.errors.institution_id)} {...form.register("institution_id")}><option value="">Select your institution</option>{institutions.data?.items.map((institution) => <option key={institution.id} value={institution.id}>{institution.name} ({institution.code})</option>)}</select>
        {form.formState.errors.institution_id ? <span className="mt-1 block text-sm text-red-700">{form.formState.errors.institution_id.message}</span> : null}
      </label>
      <label className="block text-sm font-medium text-slate-700">Application category <span className="text-red-600">*</span><Input className="mt-1" aria-invalid={Boolean(form.formState.errors.application_type)} {...form.register("application_type")} />{form.formState.errors.application_type ? <span className="mt-1 block text-sm text-red-700">{form.formState.errors.application_type.message}</span> : null}</label>
      <label className="block text-sm font-medium text-slate-700">Application title <span className="text-red-600">*</span><Input className="mt-1" aria-invalid={Boolean(form.formState.errors.title)} {...form.register("title")} />{form.formState.errors.title ? <span className="mt-1 block text-sm text-red-700">{form.formState.errors.title.message}</span> : null}</label>
      {isEdit && application.data ? <p className="rounded-md bg-slate-50 p-3 text-sm text-muted">This draft is pinned to workflow version <span className="font-mono">{application.data.workflow_template_version_id}</span>. The workflow cannot be changed after creation.</p> : null}
      <label className="block text-sm font-medium text-slate-700">Additional supported application details (JSON object)<textarea className="mt-1 min-h-40 w-full rounded-md border border-slate-300 p-3 font-mono text-sm" aria-invalid={Boolean(form.formState.errors.data_json)} {...form.register("data_json")} />{form.formState.errors.data_json ? <span className="mt-1 block text-sm text-red-700">{form.formState.errors.data_json.message}</span> : <span className="mt-1 block text-xs text-muted">Stored with the immutable application version; use a JSON object only.</span>}</label>
      {!isEdit ? <label className="block text-sm font-medium text-slate-700">Synthetic workflow route <span className="text-red-600">*</span><select className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" {...form.register("workflow_template_key")}><option value="SCRUTINY_ONLY">Scrutiny only</option><option value="SCRUTINY_THEN_EVC">Scrutiny then EVC</option><option value="EVC_THEN_SAC_SHC">EVC then SAC/SHC</option><option value="SCRUTINY_EVC_SAC_SHC">Scrutiny, EVC, then SAC/SHC</option></select></label> : null}
      <div className="flex justify-end"><Button type="submit" disabled={mutation.isPending || institutions.isLoading}><Save className="mr-2 h-4 w-4" />{mutation.isPending ? "Saving…" : "Save draft"}</Button></div>
    </form>
  </Card></div>;
}
