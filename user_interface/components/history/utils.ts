export function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-KE", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
