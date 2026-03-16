import React from 'react';

/**
 * Red-bordered error card for failed indicators.
 */
export default function ErrorCard({ title, error, note }) {
  return (
    <div className="error-card">
      {title && <div className="error-title">{title}</div>}
      <div>{error || 'Unknown error'}</div>
      {note && <div className="error-note">{note}</div>}
    </div>
  );
}
