import React from 'react';
import { useAspStore } from './stores/aspStore';
import { DecisionBox } from './components/DecisionBox';
import { Card, CardHeader, CardTitle, CardContent, Badge, cn } from './ui';

export function App(): React.ReactElement {
  const { analysis, errors, filePath } = useAspStore();

  if (!analysis) {
    return (
      <div className="flex items-center justify-center p-6 text-muted">
        <div className="w-6 h-6 border-2 border-muted border-t-transparent rounded-full animate-spin-slow" />
        <span className="ml-2">Loading analysis...</span>
      </div>
    );
  }

  const sortedDecisions = analysis.decisions
    ? Object.entries(analysis.decisions).sort(([, a], [, b]) => {
        // Sort by importance (1 = most important)
        return (a.importance || 3) - (b.importance || 3);
      })
    : [];

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <header className="mb-4">
        <h1 className="text-2xl font-semibold">
          {analysis.analysis.name}
        </h1>
        {analysis.analysis.description && (
          <p className="mt-2 text-muted">
            {analysis.analysis.description.split('\n')[0]}
          </p>
        )}
        {filePath && (
          <div className="mt-1 text-xs text-muted/70 font-mono">
            {filePath}
          </div>
        )}
      </header>

      {/* Errors */}
      {errors.length > 0 && (
        <Card variant="default" className="mb-4 border-error bg-error-background">
          <CardContent className="p-3">
            <strong className="text-error">Validation Errors:</strong>
            <ul className="mt-2 list-disc list-inside space-y-1">
              {errors.map((error, i) => (
                <li key={i}>
                  {error.message}
                  {error.path && (
                    <span className="text-muted ml-1">at {error.path}</span>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Decisions */}
      <section>
        <h2 className="text-lg font-semibold mb-3 text-muted">
          Decisions ({sortedDecisions.length})
        </h2>

        {sortedDecisions.map(([id, decision]) => (
          <DecisionBox key={id} decisionId={id} decision={decision} />
        ))}

        {sortedDecisions.length === 0 && (
          <div className="text-muted italic">
            No decisions defined in this analysis.
          </div>
        )}
      </section>

      {/* Inputs summary */}
      {analysis.analysis.inputs?.length > 0 && (
        <section className="mt-6">
          <h2 className="text-lg font-semibold mb-3 text-muted">
            Inputs ({analysis.analysis.inputs.length})
          </h2>
          <div className="flex flex-wrap gap-2">
            {analysis.analysis.inputs.map((input) => (
              <Badge key={input.id} variant="default">
                {input.id}
              </Badge>
            ))}
          </div>
        </section>
      )}

      {/* Outputs summary */}
      {analysis.analysis.outputs?.length > 0 && (
        <section className="mt-6">
          <h2 className="text-lg font-semibold mb-3 text-muted">
            Outputs ({analysis.analysis.outputs.length})
          </h2>
          <div className="flex flex-wrap gap-2">
            {analysis.analysis.outputs.map((output) => (
              <Badge
                key={output.id}
                variant={output.primary ? 'success' : 'default'}
              >
                {output.id}
                {output.primary && ' (primary)'}
              </Badge>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
