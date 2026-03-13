"use client";

import { useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthPageShell } from "@/components/auth/AuthPageShell";
import { FormError } from "@/components/auth/FormError";
import { SuccessCard } from "@/components/auth/SuccessCard";
import { apiFetch } from "@/lib/api";

/**
 * Activate form — reads the one-time token from the URL query string,
 * validates client-side, then calls the backend to set the password and
 * flip the account status to "active".
 *
 * Wrapped in `<Suspense>` by the parent page because `useSearchParams`
 * requires it in the Next.js App Router.
 */
function ActivateForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState("");
  const [success, setSuccess] = useState(false);

  // Derive the missing-token error without an effect — token is synchronous.
  const tokenError = token ? "" : "No activation token found. Check your activation link.";
  const error = tokenError || apiError;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirmPassword) { setApiError("Passwords do not match"); return; }
    if (password.length < 8) { setApiError("Password must be at least 8 characters"); return; }

    setLoading(true);
    setApiError("");
    try {
      await apiFetch("/api/v1/auth/activate", {
        method: "POST",
        body: JSON.stringify({ token, password, confirm_password: confirmPassword }),
        skipAuth: true,
      });
      setSuccess(true);
    } catch (err) {
      setApiError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <SuccessCard
        title="Account Activated"
        message="Your account is ready. You can now sign in with your new password."
        linkHref="/login"
        linkLabel="Sign in"
      />
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Set Your Password</h2>
        <p className="text-sm text-gray-500 mt-1">
          Choose a password to activate your account
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">New Password</Label>
        <Input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          disabled={loading || !token}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirmPassword">Confirm Password</Label>
        <Input
          id="confirmPassword"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          autoComplete="new-password"
          disabled={loading || !token}
        />
      </div>

      <FormError message={error} />

      <Button
        type="submit"
        className="w-full"
        style={{ backgroundColor: "#1a3a6b" }}
        disabled={loading || !token}
      >
        {loading ? "Activating…" : "Activate Account"}
      </Button>
    </form>
  );
}

/**
 * Account activation page — reached via the `/activate?token=<uuid>` link
 * that administrators share with approved users.
 */
export default function ActivatePage() {
  return (
    <AuthPageShell>
      <Suspense
        fallback={
          <p className="text-center text-gray-400 py-4">Loading…</p>
        }
      >
        <ActivateForm />
      </Suspense>
    </AuthPageShell>
  );
}
