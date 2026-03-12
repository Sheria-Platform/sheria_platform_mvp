import { UserRole } from "@/types/api";
import { Badge } from "@/components/ui/badge";

const ROLE_STYLES: Record<UserRole, React.CSSProperties> = {
  judge: { backgroundColor: "#1a3a6b", color: "white" },
  magistrate: { backgroundColor: "#2a579e", color: "white" },
  registrar: { backgroundColor: "#2563eb", color: "white" },
  clerk: { backgroundColor: "#6b7280", color: "white" },
  admin: { backgroundColor: "#b5121b", color: "white" },
};

const ROLE_LABELS: Record<UserRole, string> = {
  judge: "Judge",
  magistrate: "Magistrate",
  registrar: "Registrar",
  clerk: "Clerk",
  admin: "Admin",
};

export function RoleBadge({ role }: { role: UserRole }) {
  return (
    <Badge className="text-xs font-medium" style={ROLE_STYLES[role]}>
      {ROLE_LABELS[role]}
    </Badge>
  );
}
