import React, { useEffect, useState } from 'react';
import { fetchCalendar } from '../api';

/**
 * Next macro catalysts, read from historical_data/macro_catalyst_calendar.csv
 * via /api/calendar. The CSV was already being produced for the options
 * strategy downstream but was never surfaced on the dashboard.
 *
 * Fetched after first paint and rendered as a thin strip — a trader's first
 * question looking at a macro screen is usually "what prints next, and when".
 */
export default function CalendarStrip() {
  const [events, setEvents] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchCalendar(45, 8)
      .then((d) => {
        if (cancelled) return;
        if (d.error) setErr(d.error);
        else setEvents(d.events || []);
      })
      .catch((e) => !cancelled && setErr(e.message));
    return () => { cancelled = true; };
  }, []);

  if (err) return <div className="calendar-strip calendar-strip-err">Calendar unavailable: {err}</div>;
  if (!events) return null;
  if (events.length === 0) {
    return <div className="calendar-strip">No macro catalysts in the next 45 days.</div>;
  }

  const badge = (d) => (d <= 1 ? 'imminent' : d <= 7 ? 'soon' : 'later');

  return (
    <div className="calendar-strip">
      <span className="calendar-label">Next catalysts</span>
      {events.map((e, i) => (
        <span key={`${e.date}-${i}`} className={`calendar-item calendar-${badge(e.days_until)}`}>
          <span className="calendar-countdown">
            {e.days_until === 0 ? 'TODAY' : `T-${e.days_until}`}
          </span>
          <span className={`calendar-name imp-${e.importance || 'medium'}`}>{e.name}</span>
          <span className="calendar-date">{e.date.slice(5)}</span>
        </span>
      ))}
    </div>
  );
}
