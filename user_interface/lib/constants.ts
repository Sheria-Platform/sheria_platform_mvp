import { UserRole } from "@/types/api";

/**
 * Judicial roles available for self-registration.
 * Does not include "admin" — admin accounts are created by existing admins only.
 */
export const JUDICIAL_ROLES: { value: UserRole; label: string }[] = [
  { value: "judge",      label: "Judge" },
  { value: "magistrate", label: "Magistrate" },
  { value: "registrar",  label: "Court Registrar" },
  { value: "clerk",      label: "Judicial Clerk" },
];

/**
 * All assignable roles including admin.
 * Used in the admin approval panel where an administrator can
 * override the role requested during registration.
 */
export const ALL_ROLES: { value: UserRole; label: string }[] = [
  ...JUDICIAL_ROLES,
  { value: "admin", label: "Administrator" },
];

/**
 * Kenya court station options for the registration form.
 * Listed roughly by court hierarchy then alphabetically within tier.
 */
export const COURT_STATIONS: string[] = [
  "Supreme Court",
  "Court of Appeal Nairobi",
  "Court of Appeal Mombasa",
  "High Court Nairobi",
  "High Court Mombasa",
  "High Court Kisumu",
  "High Court Nakuru",
  "High Court Eldoret",
  "Milimani Commercial Courts",
  "Milimani Law Courts",
  "Other",
];
