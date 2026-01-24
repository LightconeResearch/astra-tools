import React from 'react';
import { useAspStore } from './stores/aspStore';
import { UniverseBuilder } from './components/UniverseBuilder';

export function UniverseBuilderApp(): React.ReactElement {
  const { analysis, errors } = useAspStore();

  if (!analysis) {
    return (
      <div className="loading">
        <div className="loading-spinner" />
        <span style={{ marginLeft: 8 }}>Loading analysis...</span>
      </div>
    );
  }

  return (
    <div className="universe-builder-app">
      {/* Header */}
      <header style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
          Universe Builder
        </h1>
        <p style={{ margin: '4px 0 0', fontSize: 12, opacity: 0.7 }}>
          {analysis.analysis.name}
        </p>
      </header>

      {/* Errors */}
      {errors.length > 0 && (
        <div className="error-message" style={{ marginBottom: 16 }}>
          <strong>Analysis has errors - universe building may not work correctly</strong>
        </div>
      )}

      {/* Universe Builder */}
      <UniverseBuilder />
    </div>
  );
}
