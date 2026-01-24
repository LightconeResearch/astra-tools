import React, { useState, useEffect } from 'react';
import { useAspStore } from '../stores/aspStore';

export function UniverseBuilder(): React.ReactElement {
  const {
    analysis,
    currentSelections,
    validOptions,
    universes,
    updateSelection,
    sendMessage,
  } = useAspStore();

  const [universeName, setUniverseName] = useState('');
  const [validationStatus, setValidationStatus] = useState<{
    valid: boolean;
    errors: string[];
  } | null>(null);

  // Request valid options whenever selections change
  useEffect(() => {
    if (analysis?.decisions) {
      for (const decisionId of Object.keys(analysis.decisions)) {
        sendMessage({
          type: 'getValidOptions',
          decisionId,
          currentSelections,
        });
      }
    }
  }, [currentSelections, analysis?.decisions]);

  // Validate on selection change
  useEffect(() => {
    sendMessage({
      type: 'validateUniverse',
      selections: currentSelections,
    });
  }, [currentSelections]);

  // Handle validation result from extension
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const message = event.data;
      if (message.type === 'validationResult') {
        setValidationStatus({
          valid: message.valid,
          errors: message.errors || [],
        });
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  const handleSave = () => {
    if (!universeName.trim()) {
      return;
    }
    sendMessage({
      type: 'saveUniverse',
      name: universeName.trim(),
      selections: currentSelections,
    });
    setUniverseName('');
  };

  const handleLoadUniverse = (selections: Record<string, string>) => {
    for (const [decisionId, optionId] of Object.entries(selections)) {
      updateSelection(decisionId, optionId);
    }
  };

  if (!analysis?.decisions) {
    return <div style={{ opacity: 0.6 }}>No decisions in this analysis.</div>;
  }

  const decisions = Object.entries(analysis.decisions).sort(([, a], [, b]) => {
    return (a.importance || 3) - (b.importance || 3);
  });

  return (
    <div className="universe-builder">
      {/* Validation status */}
      {validationStatus && (
        <div
          className={validationStatus.valid ? 'success-message' : 'error-message'}
          style={{ marginBottom: 16 }}
        >
          {validationStatus.valid ? (
            '✓ Universe configuration is valid'
          ) : (
            <>
              <strong>⚠ Constraint violations:</strong>
              <ul style={{ margin: '8px 0 0', paddingLeft: 20 }}>
                {validationStatus.errors.map((error, i) => (
                  <li key={i}>{error}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* Decision selectors */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {decisions.map(([decisionId, decision]) => (
          <DecisionSelector
            key={decisionId}
            decisionId={decisionId}
            decision={decision}
            selectedOption={currentSelections[decisionId]}
            validOptions={validOptions[decisionId] || {}}
            onSelect={(optionId) => updateSelection(decisionId, optionId)}
          />
        ))}
      </div>

      {/* Save section */}
      <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--vscode-panel-border)' }}>
        <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
          Save Universe
        </h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            className="input"
            type="text"
            placeholder="Universe name..."
            value={universeName}
            onChange={(e) => setUniverseName(e.target.value)}
            style={{ flex: 1 }}
          />
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!universeName.trim() || !validationStatus?.valid}
          >
            Save
          </button>
        </div>
      </div>

      {/* Existing universes */}
      {universes.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
            Existing Universes
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {universes.map((universe) => (
              <div
                key={universe.name}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 12px',
                  background: 'var(--vscode-input-background)',
                  borderRadius: 4,
                }}
              >
                <span style={{ fontWeight: 500 }}>{universe.name}</span>
                <button
                  className="btn btn-secondary"
                  onClick={() => handleLoadUniverse(universe.selections)}
                  style={{ padding: '4px 8px', fontSize: 11 }}
                >
                  Load
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface DecisionSelectorProps {
  decisionId: string;
  decision: {
    label: string;
    type: string;
    importance?: number;
    rationale?: string;
    default?: string;
    options: Record<string, { label: string; description?: string }>;
  };
  selectedOption: string;
  validOptions: Record<string, { valid: boolean; reason?: string }>;
  onSelect: (optionId: string) => void;
}

function DecisionSelector({
  decisionId,
  decision,
  selectedOption,
  validOptions,
  onSelect,
}: DecisionSelectorProps): React.ReactElement {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <label style={{ fontWeight: 500, fontSize: 13 }}>{decision.label}</label>
        <span className={`type-badge ${decision.type}`} style={{ fontSize: 9 }}>
          {decision.type}
        </span>
      </div>
      {decision.rationale && (
        <div style={{ fontSize: 11, opacity: 0.6, marginBottom: 6 }}>
          {decision.rationale}
        </div>
      )}
      <select
        className="select"
        value={selectedOption}
        onChange={(e) => onSelect(e.target.value)}
        style={{ width: '100%' }}
      >
        {Object.entries(decision.options).map(([optionId, option]) => {
          const validity = validOptions[optionId] ?? { valid: true };
          const isDefault = decision.default === optionId;

          return (
            <option
              key={optionId}
              value={optionId}
              disabled={!validity.valid}
              style={{ color: validity.valid ? 'inherit' : 'gray' }}
            >
              {option.label}
              {isDefault ? ' (default)' : ''}
              {!validity.valid && validity.reason ? ` - ${validity.reason}` : ''}
            </option>
          );
        })}
      </select>
    </div>
  );
}
