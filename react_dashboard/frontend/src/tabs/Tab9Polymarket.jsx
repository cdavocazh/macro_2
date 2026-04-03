import React, { useState } from 'react';
import SectionHeader from '../components/SectionHeader';
import PolymarketPriceChart from '../components/PolymarketPriceChart';

function fmtVol(v) {
  if (v == null || v === 0) return '$0';
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function EventCard({ event }) {
  if (!event) return null;

  const yesPct = event.yes_pct || 0;
  const pctColor = yesPct >= 50 ? '#26a69a' : '#ef5350';
  const outcomes = event.outcomes || [];
  const isMultiOutcome = event.num_markets > 1 && outcomes.length > 1;
  const eventUrl = event.slug
    ? `https://polymarket.com/event/${event.slug}`
    : null;

  return (
    <div style={{
      background: '#fff',
      borderRadius: 8,
      padding: '10px 14px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      borderLeft: `3px solid ${pctColor}`,
      marginBottom: 8,
    }}>
      {/* Title — links to Polymarket event page */}
      <div style={{ fontSize: '0.82rem', fontWeight: 600, lineHeight: 1.3, marginBottom: 4 }}>
        {eventUrl ? (
          <a
            href={eventUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#1565c0', textDecoration: 'none' }}
            onMouseOver={(e) => { e.target.style.textDecoration = 'underline'; }}
            onMouseOut={(e) => { e.target.style.textDecoration = 'none'; }}
          >
            {event.title}
          </a>
        ) : event.title}
      </div>

      {/* Main probability + volume */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
        <span style={{ fontSize: '1.3rem', fontWeight: 700, color: pctColor }}>
          {yesPct}%
        </span>
        <span style={{ fontSize: '0.72rem', color: '#888' }}>chance</span>
        <span style={{ fontSize: '0.72rem', color: '#888', marginLeft: 'auto' }}>
          {fmtVol(event.volume_24h)} vol (24h)
        </span>
      </div>

      {/* Multi-outcome breakdown */}
      {isMultiOutcome && (
        <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: '4px 12px' }}>
          {outcomes.slice(0, 6).map((o, i) => (
            <span key={i} style={{ fontSize: '0.68rem', color: '#666' }}>
              <span style={{
                color: o.yes_price >= 0.5 ? '#26a69a' : '#888',
                fontWeight: o.yes_price >= 0.1 ? 600 : 400,
              }}>
                {(o.yes_price * 100).toFixed(0)}%
              </span>
              {' '}{o.label?.length > 30 ? o.label.substring(0, 30) + '...' : o.label}
            </span>
          ))}
          {outcomes.length > 6 && (
            <span style={{ fontSize: '0.68rem', color: '#999' }}>
              +{outcomes.length - 6} more
            </span>
          )}
        </div>
      )}

      {/* End date */}
      {event.end_date && (
        <div style={{ fontSize: '0.65rem', color: '#aaa', marginTop: 4 }}>
          Resolves: {new Date(event.end_date).toLocaleDateString()}
        </div>
      )}

      {/* Price chart — multi-outcome with Plotly */}
      {outcomes.length > 0 && outcomes.some(o => o.token_id) && (
        <PolymarketPriceChart
          outcomes={outcomes}
          label={event.title}
        />
      )}
    </div>
  );
}

/**
 * Collapsible section with hide/show toggle button on the right.
 */
function CollapsibleSection({ title, events, gridCols = 2, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);

  if (!events || events.length === 0) return null;

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Section header row with toggle */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 8,
      }}>
        <h3 style={{
          fontSize: '0.92rem', fontWeight: 700, color: '#333', margin: 0,
          borderBottom: '2px solid #1976d2', paddingBottom: 2, display: 'inline-block',
        }}>
          {title}
          <span style={{ fontSize: '0.72rem', color: '#999', fontWeight: 400, marginLeft: 8 }}>
            ({events.length})
          </span>
        </h3>
        <button
          onClick={() => setOpen(!open)}
          style={{
            padding: '3px 12px',
            fontSize: '0.7rem',
            fontWeight: 600,
            border: '1px solid #ccc',
            borderRadius: 4,
            background: open ? '#f5f5f5' : '#e3f2fd',
            color: open ? '#666' : '#1565c0',
            cursor: 'pointer',
          }}
        >
          {open ? 'Hide' : 'Show'}
        </button>
      </div>

      {/* Event cards */}
      {open && (
        <div className={`grid-${gridCols}`}>
          {events.map((e, i) => (
            <EventCard key={e.event_id || i} event={e} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Tab9Polymarket({ indicators }) {
  if (!indicators) return null;

  const pm = indicators['86_polymarket'] || {};

  if (pm.error) {
    return (
      <div>
        <SectionHeader title="Polymarket Prediction Markets" />
        <div className="error-card">
          <div className="error-title">Polymarket Data Error</div>
          <div>{pm.error}</div>
        </div>
      </div>
    );
  }

  const part1 = pm.part1_fed_rate || [];
  const part2 = pm.part2_economy || [];
  const part3 = pm.part3_finance || [];
  const part4 = pm.part4_geopolitics || [];
  const part5 = pm.part5_trending || {};

  const noData = part1.length === 0 && part2.length === 0;

  return (
    <div>
      <SectionHeader title="Polymarket Prediction Markets" />
      <div className="metric-caption" style={{ marginBottom: 12 }}>
        Real-money prediction market odds from{' '}
        <a href="https://polymarket.com" target="_blank" rel="noopener noreferrer"
           style={{ color: '#1565c0' }}>Polymarket</a>.
        Updated every 5 minutes.
        {pm.latest_date && <> | As of: {new Date(pm.latest_date).toLocaleString()}</>}
      </div>

      {noData && (
        <div style={{ padding: 20, textAlign: 'center', color: '#888' }}>
          No Polymarket data available. Run <code>python polymarket_extract.py --force</code> to fetch.
        </div>
      )}

      <CollapsibleSection title="Fed Rate Decisions" events={part1} />
      <CollapsibleSection title="Economy (Inflation, GDP, Unemployment, SOFR)" events={part2} />
      <CollapsibleSection title="Finance (Gold, Silver, SPX, Crude Oil, Rate Cuts)" events={part3} />
      <CollapsibleSection title="Geopolitics" events={part4} />

      {Object.keys(part5).length > 0 && (
        <>
          <SectionHeader title="Trending by Category" />
          {Object.entries(part5).map(([tag, events]) => (
            <CollapsibleSection key={tag} title={`Trending: ${tag}`} events={events} />
          ))}
        </>
      )}
    </div>
  );
}
