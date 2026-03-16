import React from 'react';

/**
 * Simple wrapper that shows/hides based on active tab.
 */
export default function TabPanel({ active, children }) {
  if (!active) return null;
  return <div className="tab-content">{children}</div>;
}
