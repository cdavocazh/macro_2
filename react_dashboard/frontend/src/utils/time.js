/**
 * Time formatting utilities — convert all dashboard timestamps to GMT+8 (Asia/Singapore).
 *
 * Backend supplies timestamps in various formats:
 *   - ISO 8601 with Z or offset:  "2026-04-15T02:26:27.123Z"
 *   - ISO 8601 naive (treat UTC): "2026-04-15T02:26:27.123"
 *   - Compact w/ space:           "2026-04-15 02:26"
 *   - Date-only:                  "2026-04-15"
 *
 * All formats are parsed and rendered in Asia/Singapore (GMT+8).
 */

const TZ = 'Asia/Singapore';

/**
 * Convert any backend timestamp string to GMT+8 display string.
 * Returns 'N/A' for null/undefined/unparseable input.
 */
export function toGMT8(input, opts = {}) {
  if (input == null || input === '' || input === 'N/A') return 'N/A';

  const includeSeconds = opts.includeSeconds !== false;
  const dateOnly = opts.dateOnly === true;

  let s = String(input);

  // Normalize "YYYY-MM-DD HH:MM[:SS] UTC" -> "YYYY-MM-DDTHH:MM[:SS]Z"
  s = s.replace(' UTC', 'Z').replace(' ', 'T');

  // Date-only string ("YYYY-MM-DD") — treat as 00:00:00 UTC
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    s = s + 'T00:00:00Z';
  }

  // Naive ISO without timezone — treat as UTC
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?$/.test(s)) {
    s = s + 'Z';
  }

  const d = new Date(s);
  if (isNaN(d.getTime())) return String(input);

  const fmtOpts = {
    timeZone: TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour12: false,
  };
  if (!dateOnly) {
    fmtOpts.hour = '2-digit';
    fmtOpts.minute = '2-digit';
    if (includeSeconds) fmtOpts.second = '2-digit';
  }

  const formatted = d.toLocaleString('en-GB', fmtOpts);
  return formatted + ' GMT+8';
}

/**
 * Convenience: short form for "As of:" captions (no seconds).
 */
export function toGMT8Short(input) {
  return toGMT8(input, { includeSeconds: false });
}

/**
 * For tickers that only need the date.
 */
export function toGMT8Date(input) {
  return toGMT8(input, { dateOnly: true });
}
