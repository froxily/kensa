import { Badge, type Tone } from "../../../components/ui/Badge";
import { useStrings } from "../../../i18n";
import type { InvestigationStatus, VerificationStatus } from "../types";

const statusTone: Record<InvestigationStatus, Tone> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  failed: "danger",
};

const verificationTone: Record<VerificationStatus, Tone> = {
  corroborated: "success",
  plausible: "info",
  conflicting: "warning",
  not_established: "warning",
};

export function StatusBadge({ status }: { status: InvestigationStatus }) {
  const strings = useStrings();
  return <Badge tone={statusTone[status]}>{strings.status[status]}</Badge>;
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const strings = useStrings();
  return <Badge tone={verificationTone[status]}>{strings.verification[status]}</Badge>;
}
