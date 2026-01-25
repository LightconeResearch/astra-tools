"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useAnalysisStore } from "@/lib/stores/analysis-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { DecisionPanel } from "@/components/canvas/decision-panel";
import { Loader2 } from "lucide-react";

export function DocumentCanvas() {
  const { analysis, isLoading, loadError, isDirty } = useAnalysisStore();
  const { lodLevel, typeFilters } = useUIStore();

  if (isLoading) {
    return (
      <div className="h-full w-full flex items-center justify-center overflow-hidden">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="h-full w-full flex items-center justify-center overflow-hidden">
        <div className="text-center space-y-2">
          <p className="text-destructive font-medium">Failed to load analysis</p>
          <p className="text-sm text-muted-foreground">{loadError}</p>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="h-full w-full flex items-center justify-center overflow-hidden">
        <div className="text-center space-y-2">
          <p className="text-muted-foreground">No analysis loaded</p>
          <p className="text-sm text-muted-foreground">
            Start the backend server and refresh
          </p>
        </div>
      </div>
    );
  }

  const decisions = analysis.decisions ?? {};
  const decisionEntries = Object.entries(decisions);

  // Filter decisions by LOD and type
  const visibleDecisions = decisionEntries.filter(([, decision]) => {
    const importance = decision.importance ?? 3;
    const typeMatch = typeFilters.has(decision.type);
    const lodMatch = importance <= lodLevel;
    return typeMatch && lodMatch;
  });

  return (
    <div className="h-full w-full overflow-hidden">
      <ScrollArea className="h-full">
        <div className="max-w-4xl mx-auto py-8 px-6">
        {/* Analysis Header */}
        <header className="mb-8">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">
                {analysis.analysis.name}
              </h1>
              {analysis.analysis.authors && (
                <p className="text-sm text-muted-foreground mt-1">
                  {analysis.analysis.authors.join(", ")}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline">v{analysis.version}</Badge>
              {isDirty && (
                <Badge variant="secondary" className="text-yellow-600">
                  Unsaved
                </Badge>
              )}
            </div>
          </div>
          {analysis.analysis.tags && (
            <div className="flex gap-2 mb-4">
              {analysis.analysis.tags.map((tag) => (
                <Badge key={tag} variant="secondary">
                  {tag}
                </Badge>
              ))}
            </div>
          )}
        </header>

        {/* Problem Statement */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-2">Problem Statement</h2>
          <div className="prose prose-sm max-w-none text-muted-foreground">
            <p className="whitespace-pre-wrap">{analysis.analysis.problem}</p>
          </div>
        </section>

        {/* Description */}
        {analysis.analysis.description && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold mb-2">Description</h2>
            <div className="prose prose-sm max-w-none text-muted-foreground">
              <p className="whitespace-pre-wrap">{analysis.analysis.description}</p>
            </div>
          </section>
        )}

        {/* Decisions */}
        <section>
          <h2 className="text-lg font-semibold mb-4">
            Decisions
            <span className="text-muted-foreground font-normal ml-2">
              ({visibleDecisions.length} of {decisionEntries.length})
            </span>
          </h2>
          <div className="space-y-4">
            {visibleDecisions.map(([id, decision]) => (
              <DecisionPanel key={id} id={id} decision={decision} />
            ))}
            {visibleDecisions.length === 0 && (
              <p className="text-muted-foreground text-center py-8">
                No decisions match the current filters.
                <br />
                Adjust the LOD slider or type filters in the navigator.
              </p>
            )}
          </div>
        </section>

        {/* Inputs */}
        {analysis.analysis.inputs.length > 0 && (
          <section className="mt-8 pt-8 border-t">
            <h2 className="text-lg font-semibold mb-4">Inputs</h2>
            <div className="grid gap-3">
              {analysis.analysis.inputs.map((input) => (
                <div
                  key={input.id}
                  className="p-3 rounded-lg border bg-card text-card-foreground"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <code className="text-sm font-mono bg-muted px-1.5 py-0.5 rounded">
                      {input.id}
                    </code>
                    <Badge variant="outline" className="text-xs">
                      {input.type}
                    </Badge>
                  </div>
                  {input.description && (
                    <p className="text-sm text-muted-foreground">
                      {input.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Outputs */}
        {analysis.analysis.outputs.length > 0 && (
          <section className="mt-8 pt-8 border-t">
            <h2 className="text-lg font-semibold mb-4">Outputs</h2>
            <div className="grid gap-3">
              {analysis.analysis.outputs.map((output) => (
                <div
                  key={output.id}
                  className="p-3 rounded-lg border bg-card text-card-foreground"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <code className="text-sm font-mono bg-muted px-1.5 py-0.5 rounded">
                      {output.id}
                    </code>
                    <Badge variant="outline" className="text-xs">
                      {output.type}
                    </Badge>
                    {output.primary && (
                      <Badge className="text-xs">Primary</Badge>
                    )}
                  </div>
                  {output.description && (
                    <p className="text-sm text-muted-foreground">
                      {output.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
        </div>
      </ScrollArea>
    </div>
  );
}
