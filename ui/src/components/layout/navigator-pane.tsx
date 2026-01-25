"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { useAnalysisStore } from "@/lib/stores/analysis-store";
import { useUIStore } from "@/lib/stores/ui-store";
import type { DecisionType } from "@/lib/types";
import { cn } from "@/lib/utils";

const typeColors: Record<DecisionType, string> = {
  data: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  method: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  parameter: "bg-orange-500/10 text-orange-500 border-orange-500/20",
};

const importanceLabels = ["", "Critical", "Important", "Normal", "Minor", "Detail"];

export function NavigatorPane() {
  const { analysis } = useAnalysisStore();
  const {
    lodLevel,
    setLOD,
    typeFilters,
    toggleTypeFilter,
    focusedDecisionId,
    setFocus,
  } = useUIStore();

  const decisions = analysis?.decisions ?? {};
  const decisionEntries = Object.entries(decisions);

  // Filter decisions by LOD and type
  const visibleDecisions = decisionEntries.filter(([, decision]) => {
    const importance = decision.importance ?? 3;
    const typeMatch = typeFilters.has(decision.type);
    const lodMatch = importance <= lodLevel;
    return typeMatch && lodMatch;
  });

  const scrollToDecision = (decisionId: string) => {
    setFocus(decisionId, null);
    const element = document.getElementById(`decision-${decisionId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="h-full w-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b">
        <h2 className="font-semibold text-sm mb-3">Navigator</h2>

        {/* LOD Slider */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Detail Level</span>
            <span className="font-medium">{importanceLabels[lodLevel]}</span>
          </div>
          <Slider
            value={[lodLevel]}
            onValueChange={([value]) => setLOD(value)}
            min={1}
            max={5}
            step={1}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Critical</span>
            <span>All</span>
          </div>
        </div>
      </div>

      {/* Type Filters */}
      <div className="p-4 border-b space-y-2">
        <span className="text-xs text-muted-foreground">Filter by type</span>
        <div className="flex flex-wrap gap-2">
          {(["data", "method", "parameter"] as DecisionType[]).map((type) => (
            <label
              key={type}
              className="flex items-center gap-1.5 cursor-pointer"
            >
              <Checkbox
                checked={typeFilters.has(type)}
                onCheckedChange={() => toggleTypeFilter(type)}
              />
              <span className="text-xs capitalize">{type}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Table of Contents */}
      <ScrollArea className="flex-1">
        <div className="p-2">
          <h3 className="text-xs font-medium text-muted-foreground px-2 mb-2">
            Decisions ({visibleDecisions.length}/{decisionEntries.length})
          </h3>
          <nav className="space-y-0.5">
            {visibleDecisions.map(([id, decision]) => {
              const importance = decision.importance ?? 3;
              const isActive = focusedDecisionId === id;

              return (
                <button
                  key={id}
                  onClick={() => scrollToDecision(id)}
                  className={cn(
                    "w-full text-left px-2 py-1.5 rounded-md text-sm transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    isActive && "bg-accent text-accent-foreground"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={cn("text-[10px] px-1", typeColors[decision.type])}
                    >
                      {decision.type[0].toUpperCase()}
                    </Badge>
                    <span className="truncate flex-1">{decision.label}</span>
                    <span className="text-xs text-muted-foreground">
                      {"★".repeat(6 - importance)}
                    </span>
                  </div>
                </button>
              );
            })}
            {visibleDecisions.length === 0 && (
              <p className="text-xs text-muted-foreground px-2 py-4 text-center">
                No decisions match filters
              </p>
            )}
          </nav>
        </div>
      </ScrollArea>
    </div>
  );
}
