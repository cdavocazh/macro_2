import React, { useEffect, useRef } from 'react';

/**
 * TradingView Advanced Chart widget (free tier, attribution retained).
 *
 * Only mounted from inside the chart drawer, never on first paint — the embed
 * pulls ~1 MB of third-party script and would undo the lite-payload/lazy-plotly
 * work that got first visit to ~1.5 s.
 *
 * The widget renders its own iframe and owns everything inside it: indicators,
 * drawing tools, timeframes, compare. We deliberately do NOT try to sync it
 * with the native charts — it's a separate data source (TradingView's own
 * feed), so a shared crosshair would imply an alignment we can't guarantee.
 */
export default function TradingViewWidget({ symbol, interval = 'D', height = '100%' }) {
  const containerRef = useRef(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !symbol) return;

    // Clear any previous embed (symbol change re-mounts the widget)
    container.innerHTML = '';

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.height = 'calc(100% - 32px)';
    widgetDiv.style.width = '100%';

    // Attribution block — required by the free-widget terms.
    const copyright = document.createElement('div');
    copyright.className = 'tradingview-widget-copyright';
    copyright.innerHTML =
      `<a href="https://www.tradingview.com/symbols/${encodeURIComponent(symbol)}/" ` +
      `rel="noopener nofollow" target="_blank">` +
      `<span class="blue-text">${symbol} chart</span></a>` +
      `<span class="trademark"> by TradingView</span>`;

    container.appendChild(widgetDiv);
    container.appendChild(copyright);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: 'Asia/Singapore', // GMT+8, matching the rest of the dashboard
      theme: 'light',
      style: '1',
      locale: 'en',
      enable_publishing: false,
      withdateranges: true,
      hide_side_toolbar: false, // keep drawing tools — the point of using TV
      allow_symbol_change: true,
      details: true,
      studies: ['STD;SMA'],
      support_host: 'https://www.tradingview.com',
    });

    container.appendChild(script);

    return () => {
      // Tear the embed down on close so its timers/sockets don't linger.
      container.innerHTML = '';
    };
  }, [symbol, interval]);

  return (
    <div
      className="tradingview-widget-container"
      ref={containerRef}
      style={{ height, width: '100%' }}
    />
  );
}
