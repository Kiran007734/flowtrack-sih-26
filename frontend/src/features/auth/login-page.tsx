import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardCheck, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/auth-context";

const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { login, isAuthenticated, isBusy } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  if (isAuthenticated) return <Navigate to="/applications" replace />;

  const onSubmit = async (values: LoginValues) => {
    setError(null);
    try {
      await login(values.email, values.password);
      const returnTo = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || "/applications";
      navigate(returnTo, { replace: true });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 0) {
        setError("Unable to reach FlowTrack. Check that the API is running and try again.");
      } else if (caught instanceof ApiError && caught.status >= 500) {
        setError("FlowTrack could not sign you in right now. Please try again shortly.");
      } else {
        setError(caught instanceof ApiError ? caught.message : "Unable to sign in. Please try again.");
      }
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <Card className="w-full max-w-md p-7 sm:p-8">
        <div className="mb-7 flex items-center gap-3">
          <div className="rounded-lg bg-blue-50 p-2 text-primary"><ClipboardCheck aria-hidden="true" className="h-6 w-6" /></div>
          <div><h1 className="text-xl font-semibold text-slate-900">AICTE FlowTrack</h1><p className="text-sm text-muted">Prototype workflow workspace</p></div>
        </div>
        <h2 className="text-lg font-semibold text-slate-900">Sign in</h2>
        <p className="mt-1 text-sm text-muted">Use a local development account to access your authorized records.</p>
        <form className="mt-6 space-y-4" noValidate onSubmit={handleSubmit(onSubmit)}>
          {error ? <Alert>{error}</Alert> : null}
          <label className="block text-sm font-medium text-slate-700">Email address
            <Input autoComplete="email" className="mt-1" aria-invalid={Boolean(errors.email)} {...register("email")} />
            {errors.email ? <span className="mt-1 block text-sm text-red-700">{errors.email.message}</span> : null}
          </label>
          <label className="block text-sm font-medium text-slate-700">Password
            <span className="relative mt-1 block">
              <Input type={showPassword ? "text" : "password"} autoComplete="current-password" className="pr-12" aria-invalid={Boolean(errors.password)} {...register("password")} />
              <button type="button" className="absolute inset-y-0 right-0 px-3 text-slate-500 hover:text-slate-700" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((visible) => !visible)}>
                {showPassword ? <EyeOff aria-hidden="true" className="h-4 w-4" /> : <Eye aria-hidden="true" className="h-4 w-4" />}
              </button>
            </span>
            {errors.password ? <span className="mt-1 block text-sm text-red-700">{errors.password.message}</span> : null}
          </label>
          <Button className="w-full" type="submit" disabled={isBusy}><LockKeyhole aria-hidden="true" className="mr-2 h-4 w-4" />{isBusy ? "Signing in…" : "Sign in"}</Button>
          <p className="text-center text-sm text-muted">Need an account? <Link className="font-medium text-primary hover:underline" to="/signup">Create an account</Link></p>
        </form>
      </Card>
    </main>
  );
}
