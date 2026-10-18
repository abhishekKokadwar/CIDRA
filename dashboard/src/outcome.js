// What a run ended as, for its badge. Read from `outcome`, not `status`: the
// telemetry's status is a colour bucket, and calls a finished diagnosis "pending".
const BADGES = {
  verified_fix: { status: 'success', label: 'Verified fix' },
  diagnosis_only: { status: 'active', label: 'Diagnosis only' },
  flaky_detected: { status: 'pending', label: 'Flaky test' },
};

export function outcomeBadge(run) {
  return BADGES[run?.outcome] || { status: 'error', label: 'Failed' };
}
