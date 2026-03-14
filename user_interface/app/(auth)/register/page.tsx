"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthPageShell } from "@/components/auth/AuthPageShell";
import { FormError } from "@/components/auth/FormError";
import { SuccessCard } from "@/components/auth/SuccessCard";
import { apiFetch } from "@/lib/api";
import { JUDICIAL_ROLES, COURT_STATIONS } from "@/lib/constants";
import { RegisterRequest, UserRole } from "@/types/api";

/**
 * Registration request page.
 *
 * Judicial staff submit their details here. The request is stored with
 * status "pending" and must be approved by a court administrator before
 * the account can be activated. No credentials are collected at this step.
 */
export default function RegisterPage() {
  const [form, setForm] = useState<RegisterRequest>({
    username: "",
    email: "",
    full_name: "",
    court_station: "",
    role: "clerk" as UserRole,
    staff_number: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  function setField(field: keyof RegisterRequest, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.username || !form.email || !form.full_name || !form.court_station) {
      setError("Please fill in all required fields.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await apiFetch("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify(form),
        skipAuth: true,
      });
      setSuccess(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthPageShell>
      {success ? (
        <SuccessCard
          title="Request Submitted"
          message="Your registration request has been received. A court administrator will review it and send you an activation link once approved."
          linkHref="/login"
          linkLabel="Back to Sign in"
        />
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Request Access</h2>
            <p className="text-sm text-gray-500 mt-1">
              Submit your details for administrator approval
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="full_name">
              Full Name <span className="text-red-500">*</span>
            </Label>
            <Input
              id="full_name"
              value={form.full_name}
              onChange={(e) => setField("full_name", e.target.value)}
              placeholder="Hon. Jane Mwangi"
              disabled={loading}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="username">
                Username <span className="text-red-500">*</span>
              </Label>
              <Input
                id="username"
                value={form.username}
                onChange={(e) => setField("username", e.target.value)}
                placeholder="j.mwangi"
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="staff_number">Staff Number</Label>
              <Input
                id="staff_number"
                value={form.staff_number ?? ""}
                onChange={(e) => setField("staff_number", e.target.value)}
                placeholder="JSC-12345"
                disabled={loading}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">
              Official Email <span className="text-red-500">*</span>
            </Label>
            <Input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => setField("email", e.target.value)}
              placeholder="j.mwangi@judiciary.go.ke"
              disabled={loading}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="role">
              Role <span className="text-red-500">*</span>
            </Label>
            <select
              id="role"
              value={form.role}
              onChange={(e) => setField("role", e.target.value)}
              className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={loading}
            >
              {JUDICIAL_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="court_station">
              Court Station <span className="text-red-500">*</span>
            </Label>
            <select
              id="court_station"
              value={form.court_station}
              onChange={(e) => setField("court_station", e.target.value)}
              className="w-full border border-input bg-background rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              disabled={loading}
            >
              <option value="">Select court station…</option>
              {COURT_STATIONS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <FormError message={error} />

          <Button
            type="submit"
            className="w-full"
            style={{ backgroundColor: "#1a3a6b" }}
            disabled={loading}
          >
            {loading ? "Submitting…" : "Submit Request"}
          </Button>

          <p className="text-center text-sm text-gray-500">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-medium hover:underline"
              style={{ color: "#1a3a6b" }}
            >
              Sign in
            </Link>
          </p>
        </form>
      )}
    </AuthPageShell>
  );
}
