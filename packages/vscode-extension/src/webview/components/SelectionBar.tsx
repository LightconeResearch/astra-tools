import React from 'react';
import { useAspStore } from '../stores/aspStore';

/**
 * Floating bar that appears when an element is selected.
 * Provides a "Share with Claude" button to send the selection to Claude Code.
 */
export function SelectionBar(): React.ReactElement | null {
  const { selection, analysis, sendMessage } = useAspStore();

  if (!selection) {
    return null;
  }

  // Get a readable label for the selection
  const getSelectionLabel = () => {
    if (selection.type === 'decision' && selection.decisionId) {
      const decision = analysis?.decisions?.[selection.decisionId];
      return decision?.label || selection.decisionId;
    }
    if (selection.type === 'option' && selection.decisionId && selection.optionId) {
      const decision = analysis?.decisions?.[selection.decisionId];
      const option = decision?.options?.[selection.optionId];
      return `${decision?.label || selection.decisionId} → ${option?.label || selection.optionId}`;
    }
    return selection.type;
  };

  const handleShareWithClaude = () => {
    sendMessage({ type: 'shareWithClaude' });
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 16,
        left: 16,
        right: 16,
        background: 'var(--vscode-editor-background)',
        border: '1px solid var(--vscode-focusBorder)',
        borderRadius: 6,
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
        zIndex: 100,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ opacity: 0.6, fontSize: 12 }}>Selected:</span>
        <span
          style={{
            fontWeight: 500,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {getSelectionLabel()}
        </span>
      </div>

      <button
        className="btn btn-primary"
        onClick={handleShareWithClaude}
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span style={{ fontSize: 14 }}>✱</span>
        Share with Claude
      </button>
    </div>
  );
}
