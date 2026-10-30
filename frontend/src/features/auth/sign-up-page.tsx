import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardCheck, Eye, EyeOff, UserPlus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { api, ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const signUpSchema = z.object({
  display_name: z.string().trim().min(2, "Enter your full name.").max(255),
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(12, "Use at least 12 characters for your password.").max(256),
  confirmPassword: z.string().min(1, "Confirm your password."),
}).refine((values) => values.password === values.confirmPassword, {
  path: ["confirmPassword"],
  message: "Passwords do not match.",
});
type SignUpValues = z.infer<typeof signUpSchema>;

function registrationError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Unable to create your account request. Please try again.";
  if (error.status === 0) return "Unable to reach FlowTrack. Check that the API is running and try again.";
  if (error.status >= 500) return "FlowTrack could not create your account request right now. Please try again shortly.";
  return error.message;
}

export function SignUpPage() {
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<SignUpValues>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { display_name: "", email: "", password: "", confirmPassword: "" },
  });

  const onSubmit = async (values: SignUpValues) => {
    setError(null);
    setSuccess(null);
    try {
      const response = await api.register({
        display_name: values.display_name,
        email: values.email,
        password: values.password,
      });
      setSuccess(response.message);
    } catch (caught) {
      setError(registrationError(caught));
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <Card className="w-full max-w-md p-7 sm:p-8">
        <div className="mb-7 flex items-center gap-3">
          <div className="rounded-lg bg-blue-50 p-2 text-primary"><ClipboardCheck aria-hidden="true" className="h-6 w-6" /></div>
          <div><h1 className="text-xl font-semibold text-slate-900">AICTE FlowTrack</h1><p className="text-sm text-muted">Prototype workflow workspace</p></div>
        </div>
        <h2 className="text-lg font-semibold text-slate-900">Create an account</h2>
        <p className="mt-1 text-sm text-muted">Account requests are reviewed by an administrator before access is granted.</p>
        <form className="mt-6 space-y-4" noValidate onSubmit={handleSubmit(onSubmit)}>
          {error ? <Alert>{error}</Alert> : null}
          {success ? <Alert>{success}</Alert> : null}
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="sign-up-display-name">Full name</label>
            <Input id="sign-up-display-name" autoComplete="name" className="mt-1" aria-invalid={Boolean(errors.display_name)} disabled={Boolean(success)} {...register("display_name")} />
            {errors.display_name ? <span className="mt-1 block text-sm text-red-700">{errors.display_name.message}</span> : null}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="sign-up-email">Email address</label>
            <Input id="sign-up-email" autoComplete="email" className="mt-1" aria-invalid={Boolean(errors.email)} disabled={Boolean(success)} {...register("email")} />
            {errors.email ? <span className="mt-1 block text-sm text-red-700">{errors.email.message}</span> : null}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="sign-up-password">Password</label>
            <span className="relative mt-1 block">
              <Input id="sign-up-password" type={showPassword ? "text" : "password"} autoComplete="new-password" className="pr-12" aria-invalid={Boolean(errors.password)} disabled={Boolean(success)} {...register("password")} />
              <button type="button" className="absolute inset-y-0 right-0 px-3 text-slate-500 hover:text-slate-700 disabled:cursor-not-allowed" aria-label={showPassword ? "Hide password" : "Show password"} disabled={Boolean(success)} onClick={() => setShowPassword((visible) => !visible)}>
                {showPassword ? <EyeOff aria-hidden="true" className="h-4 w-4" /> : <Eye aria-hidden="true" className="h-4 w-4" />}
              </button>
            </span>
            {errors.password ? <span className="mt-1 block text-sm text-red-700">{errors.password.message}</span> : <span className="mt-1 block text-xs text-muted">Use at least 12 characters.</span>}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="sign-up-confirm-password">Confirm password</label>
            <Input id="sign-up-confirm-password" type={showPassword ? "text" : "password"} autoComplete="new-password" className="mt-1" aria-invalid={Boolean(errors.confirmPassword)} disabled={Boolean(success)} {...register("confirmPassword")} />
            {errors.confirmPassword ? <span className="mt-1 block text-sm text-red-700">{errors.confirmPassword.message}</span> : null}
          </div>
          <Button className="w-full" type="submit" disabled={isSubmitting || Boolean(success)}><UserPlus aria-hidden="true" className="mr-2 h-4 w-4" />{isSubmitting ? "Creating account…" : "Create account"}</Button>
          <p className="text-center text-sm text-muted">Already have an account? <Link className="font-medium text-primary hover:underline" to="/login">Sign in</Link></p>
        </form>
      </Card>
    </main>
  );
}
