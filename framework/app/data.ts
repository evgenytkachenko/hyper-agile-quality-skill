/** Fictional records only; never load patient data or credentials into this demo. */
export const labs: Record<string, { id: string; patientId: string; test: string; value: number; unit: string }> = {
  'lab-a': { id: 'lab-a', patientId: 'patient-a', test: 'Synthetic glucose', value: 90, unit: 'mg/dL' },
  'lab-b': { id: 'lab-b', patientId: 'patient-b', test: 'Synthetic glucose', value: 185, unit: 'mg/dL' }
};
// Public synthetic session identifiers are fixtures, not production credentials.
const sessions: Record<string, string> = { 'demo-session-a': 'patient-a', 'demo-session-b': 'patient-b' };
export function principalFor(header: string | undefined): string | undefined {
  if (!header?.startsWith('Bearer ')) return undefined;
  const key = header.slice(7);
  return Object.hasOwn(sessions, key) ? sessions[key] : undefined;
}
