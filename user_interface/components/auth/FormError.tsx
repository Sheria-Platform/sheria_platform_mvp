interface FormErrorProps {
  /** Error message to display. Renders nothing when empty. */
  message: string;
}

/**
 * Inline form error banner used in all auth forms.
 *
 * Renders a destructive-coloured pill when `message` is non-empty;
 * returns `null` otherwise so callers can render it unconditionally.
 */
export function FormError({ message }: FormErrorProps) {
  if (!message) return null;
  return (
    <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">
      {message}
    </p>
  );
}
