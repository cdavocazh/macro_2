import React from 'react';

export default function SectionHeader({ title, sub = false }) {
  return <h3 className={sub ? 'sub-header' : 'section-header'}>{title}</h3>;
}
