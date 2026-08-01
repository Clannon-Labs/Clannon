/** Fixed UTC anniversary period used by the browser mock.
 *
 * Missing month-end days clamp only in that month: a Jan-31 anchor produces
 * Feb-28/29, then recovers to Mar-31 instead of drifting to the 28th forever.
 * Real entitlement remains server-owned; this helper only keeps mock behavior
 * contract-compatible and gives date rendering/tests one deterministic seam.
 */
export function fixedBillingPeriod(
  anchor: Date,
  current: Date = new Date(),
): { periodStart: string; periodEnd: string } {
  const anchorDay = anchor.getUTCDate();
  const year = current.getUTCFullYear();
  const month = current.getUTCMonth();
  const thisBoundary = boundary(year, month, anchorDay);
  const currentDay = Date.UTC(year, month, current.getUTCDate());

  const start = currentDay >= thisBoundary.getTime()
    ? thisBoundary
    : boundary(year, month - 1, anchorDay);
  const end = currentDay >= thisBoundary.getTime()
    ? boundary(year, month + 1, anchorDay)
    : thisBoundary;

  return { periodStart: isoDate(start), periodEnd: isoDate(end) };
}

function boundary(year: number, month: number, anchorDay: number): Date {
  const normalized = new Date(Date.UTC(year, month, 1));
  const lastDay = new Date(
    Date.UTC(normalized.getUTCFullYear(), normalized.getUTCMonth() + 1, 0),
  ).getUTCDate();
  return new Date(
    Date.UTC(
      normalized.getUTCFullYear(),
      normalized.getUTCMonth(),
      Math.min(anchorDay, lastDay),
    ),
  );
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}
