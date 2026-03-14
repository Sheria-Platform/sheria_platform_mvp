import Link from "next/link";
import { Button } from "@/components/ui/button";

interface SuccessCardProps {
  /** Bold heading shown below the checkmark icon. */
  title: string;
  /** Supporting text below the title. */
  message: string;
  /** Destination for the call-to-action button. */
  linkHref: string;
  /** Label for the call-to-action button. */
  linkLabel: string;
}

/**
 * Full-card success state with a green checkmark, a message, and a
 * navigation call-to-action.
 *
 * Used after successful form submissions (registration request, account
 * activation) to replace the form with a confirmation view.
 */
export function SuccessCard({ title, message, linkHref, linkLabel }: SuccessCardProps) {
  return (
    <div className="text-center space-y-4">
      <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto">
        <svg
          className="w-7 h-7 text-green-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
      <p className="text-gray-600 text-sm">{message}</p>
      <Link href={linkHref}>
        <Button className="w-full mt-2" style={{ backgroundColor: "#1a3a6b" }}>
          {linkLabel}
        </Button>
      </Link>
    </div>
  );
}
