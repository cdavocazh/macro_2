import React, { Suspense, lazy } from 'react';

// plotly.js-dist-min is ~4.5 MB minified — the bulk of the app bundle. Every
// chart is inside a collapsed <details> and renders only on expand, so loading
// plotly eagerly made first paint parse megabytes of script nobody may use.
// React.lazy moves it into its own chunk, fetched on the first chart expand.
const Plot = lazy(() => import('react-plotly.js'));

export default function LazyPlot(props) {
  return (
    <Suspense fallback={<div className="metric-caption">Loading chart…</div>}>
      <Plot {...props} />
    </Suspense>
  );
}
