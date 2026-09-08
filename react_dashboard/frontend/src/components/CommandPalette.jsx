import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useChartDrawer } from './ChartDrawer';
import { TV_SYMBOLS_YF, TV_SYMBOLS_HL } from '../config/instruments';

/**
 * ⌘K / Ctrl-K command palette: jump to a tab or open an instrument's large
 * chart without hunting through eleven tabs. Modelled on the GO-bar pattern
 * every terminal has.
 */
export default function CommandPalette({ tabs, onSelectTab }) {
  const { openChart } = useChartDrawer();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef(null);

  const commands = useMemo(() => {
    const out = tabs.map((t) => ({
      kind: 'tab', id: `tab-${t.id}`, title: t.label, hint: 'Tab',
      run: () => onSelectTab(t.id),
    }));
    const label = (k) => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    for (const key of Object.keys(TV_SYMBOLS_YF)) {
      out.push({
        kind: 'chart', id: `yf-${key}`, title: label(key), hint: 'Chart',
        run: () => openChart({ source: 'yf', instrumentKey: key, label: label(key) }),
      });
    }
    for (const key of Object.keys(TV_SYMBOLS_HL)) {
      out.push({
        kind: 'chart', id: `hl-${key}`, title: `${label(key)} (Hyperliquid)`, hint: 'Chart',
        run: () => openChart({ source: 'hl', instrumentKey: key, label: label(key) }),
      });
    }
    return out;
  }, [tabs, onSelectTab, openChart]);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return commands.slice(0, 12);
    return commands.filter((c) => c.title.toLowerCase().includes(needle)).slice(0, 12);
  }, [q, commands]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
        setQ(''); setCursor(0);
      } else if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  if (!open) return null;

  const choose = (cmd) => { cmd.run(); setOpen(false); };

  const onInputKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    else if (e.key === 'Enter' && results[cursor]) { e.preventDefault(); choose(results[cursor]); }
  };

  return (
    <div className="palette-backdrop" onClick={() => setOpen(false)}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="Jump to a tab, or open a chart…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setCursor(0); }}
          onKeyDown={onInputKey}
        />
        <div className="palette-results">
          {results.length === 0 && <div className="palette-empty">No matches</div>}
          {results.map((c, i) => (
            <div
              key={c.id}
              className={`palette-row ${i === cursor ? 'active' : ''}`}
              onMouseEnter={() => setCursor(i)}
              onClick={() => choose(c)}
            >
              <span>{c.title}</span>
              <span className="palette-hint">{c.hint}</span>
            </div>
          ))}
        </div>
        <div className="palette-foot">↑↓ navigate · ⏎ open · Esc close</div>
      </div>
    </div>
  );
}
