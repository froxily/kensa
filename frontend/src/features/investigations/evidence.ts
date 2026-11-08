/** DOM id of an evidence card, so a citation of non-log evidence can bring it into view. */
export function evidenceElementId(evidenceLabel: string): string {
  return `evidence-${evidenceLabel}`;
}
