"use client";

import { useCallback } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/lib/stores/ui-store";
import { useAnalysisStore } from "@/lib/stores/analysis-store";
import type { Decision, DecisionType } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ChevronDown, AlertTriangle, Link as LinkIcon } from "lucide-react";
import { EditableText } from "./editable-text";

interface DecisionPanelProps {
  id: string;
  decision: Decision;
}

const typeColors: Record<DecisionType, string> = {
  data: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  method: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  parameter: "bg-orange-500/10 text-orange-500 border-orange-500/20",
};

function ImportanceStars({ importance }: { importance: number }) {
  const filled = 6 - importance; // importance 1 = 5 stars, importance 5 = 1 star
  return (
    <span className="text-yellow-500 text-sm tracking-tight">
      {"★".repeat(filled)}
      <span className="text-muted-foreground/30">{"★".repeat(5 - filled)}</span>
    </span>
  );
}

export function DecisionPanel({ id, decision }: DecisionPanelProps) {
  const {
    expandedDecisions,
    toggleExpanded,
    focusedDecisionId,
    focusedOptionId,
    setFocus,
  } = useUIStore();

  const { updateField } = useAnalysisStore();

  const isExpanded = expandedDecisions.has(id);
  const isFocused = focusedDecisionId === id;
  const importance = decision.importance ?? 3;
  const optionEntries = Object.entries(decision.options);

  const handleRationaleChange = useCallback(
    (value: string) => {
      updateField(["decisions", id, "rationale"], value || null);
    },
    [id, updateField]
  );

  const handleOptionDescriptionChange = useCallback(
    (optionId: string, value: string) => {
      updateField(["decisions", id, "options", optionId, "description"], value || null);
    },
    [id, updateField]
  );

  return (
    <Card
      id={`decision-${id}`}
      className={cn(
        "transition-shadow",
        isFocused && "ring-2 ring-primary ring-offset-2"
      )}
      onClick={() => setFocus(id, null)}
    >
      <Collapsible open={isExpanded} onOpenChange={() => toggleExpanded(id)}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn("text-xs", typeColors[decision.type])}
              >
                {decision.type}
              </Badge>
              <h3 className="font-semibold">{decision.label}</h3>
            </div>
            <div className="flex items-center gap-2">
              <ImportanceStars importance={importance} />
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 transition-transform",
                      isExpanded && "rotate-180"
                    )}
                  />
                </Button>
              </CollapsibleTrigger>
            </div>
          </div>
          <div className="mt-1" onClick={(e) => e.stopPropagation()}>
            <EditableText
              value={decision.rationale || ""}
              onChange={handleRationaleChange}
              placeholder="Add rationale..."
              className="text-sm text-muted-foreground"
              multiline
            />
          </div>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="pt-0">
            {/* Options Grid */}
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {optionEntries.map(([optionId, option]) => {
                const isDefault = decision.default === optionId;
                const isOptionFocused =
                  focusedDecisionId === id && focusedOptionId === optionId;
                const hasEvidence = option.evidence && option.evidence.length > 0;
                const hasConstraints =
                  (option.incompatible_with && option.incompatible_with.length > 0) ||
                  (option.requires && option.requires.length > 0);

                return (
                  <div
                    key={optionId}
                    className={cn(
                      "p-3 rounded-lg border bg-card cursor-pointer transition-colors",
                      "hover:bg-accent hover:border-accent",
                      isOptionFocused && "ring-2 ring-primary",
                      isDefault && "border-primary/50"
                    )}
                    onClick={(e) => {
                      e.stopPropagation();
                      setFocus(id, optionId);
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-sm">{option.label}</span>
                      {isDefault && (
                        <Badge variant="secondary" className="text-[10px] h-4">
                          default
                        </Badge>
                      )}
                    </div>

                    <div onClick={(e) => e.stopPropagation()}>
                      <EditableText
                        value={option.description || ""}
                        onChange={(value) => handleOptionDescriptionChange(optionId, value)}
                        placeholder="Add description..."
                        className="text-xs text-muted-foreground mb-2"
                        multiline
                      />
                    </div>

                    {/* Evidence & Constraints indicators */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {hasEvidence && (
                        <Badge variant="outline" className="text-[10px] h-4 gap-0.5">
                          <LinkIcon className="h-2.5 w-2.5" />
                          {option.evidence!.length}
                        </Badge>
                      )}
                      {option.incompatible_with && option.incompatible_with.length > 0 && (
                        <Badge
                          variant="outline"
                          className="text-[10px] h-4 gap-0.5 border-destructive/50 text-destructive"
                        >
                          <AlertTriangle className="h-2.5 w-2.5" />
                          {option.incompatible_with.length}
                        </Badge>
                      )}
                      {option.requires && option.requires.length > 0 && (
                        <Badge
                          variant="outline"
                          className="text-[10px] h-4 gap-0.5 border-blue-500/50 text-blue-500"
                        >
                          requires {option.requires.length}
                        </Badge>
                      )}
                    </div>

                    {/* Constraint details on hover/focus */}
                    {hasConstraints && isOptionFocused && (
                      <div className="mt-2 pt-2 border-t text-xs space-y-1">
                        {option.incompatible_with && option.incompatible_with.length > 0 && (
                          <div className="text-destructive">
                            <span className="font-medium">Incompatible with: </span>
                            {option.incompatible_with.join(", ")}
                          </div>
                        )}
                        {option.requires && option.requires.length > 0 && (
                          <div className="text-blue-500">
                            <span className="font-medium">Requires: </span>
                            {option.requires.join(", ")}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
