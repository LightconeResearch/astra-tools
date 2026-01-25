"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { useAnalysisStore } from "@/lib/stores/analysis-store";
import { useUIStore } from "@/lib/stores/ui-store";
import { AlertCircle, CheckCircle2, FileText, Info } from "lucide-react";

export function InspectorPane() {
  const { analysis, schemaErrors, semanticErrors, filePath } = useAnalysisStore();
  const { activeInspectorTab, setActiveInspectorTab, focusedDecisionId } =
    useUIStore();

  const totalErrors = schemaErrors.length + semanticErrors.length;
  const hasErrors = totalErrors > 0;

  // Get focused decision details
  const focusedDecision = focusedDecisionId && analysis?.decisions?.[focusedDecisionId];

  return (
    <div className="h-full w-full flex flex-col overflow-hidden">
      <Tabs
        value={activeInspectorTab}
        onValueChange={setActiveInspectorTab}
        className="flex flex-col h-full"
      >
        <div className="border-b px-2">
          <TabsList className="h-10 w-full justify-start bg-transparent">
            <TabsTrigger value="validation" className="gap-1.5 text-xs">
              {hasErrors ? (
                <AlertCircle className="h-3.5 w-3.5 text-destructive" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              )}
              Validation
              {hasErrors && (
                <Badge variant="destructive" className="ml-1 h-4 px-1 text-[10px]">
                  {totalErrors}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="details" className="gap-1.5 text-xs">
              <Info className="h-3.5 w-3.5" />
              Details
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="validation" className="flex-1 mt-0">
          <ScrollArea className="h-full">
            <div className="p-4 space-y-4">
              {!hasErrors && (
                <div className="flex items-center gap-2 text-green-600">
                  <CheckCircle2 className="h-4 w-4" />
                  <span className="text-sm">No validation errors</span>
                </div>
              )}

              {schemaErrors.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase">
                    Schema Errors
                  </h3>
                  {schemaErrors.map((error, i) => (
                    <div
                      key={i}
                      className="p-2 rounded border border-destructive/20 bg-destructive/5"
                    >
                      <code className="text-xs text-muted-foreground block mb-1">
                        {error.path}
                      </code>
                      <p className="text-sm text-destructive">{error.message}</p>
                    </div>
                  ))}
                </div>
              )}

              {semanticErrors.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase">
                    Semantic Errors
                  </h3>
                  {semanticErrors.map((error, i) => (
                    <div
                      key={i}
                      className="p-2 rounded border border-yellow-500/20 bg-yellow-500/5"
                    >
                      <code className="text-xs text-muted-foreground block mb-1">
                        {error.path}
                      </code>
                      <p className="text-sm text-yellow-600">{error.message}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="details" className="flex-1 mt-0">
          <ScrollArea className="h-full">
            <div className="p-4 space-y-4">
              {/* File info */}
              {filePath && (
                <div className="space-y-1">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase">
                    File
                  </h3>
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <code className="text-xs">{filePath}</code>
                  </div>
                </div>
              )}

              {/* Analysis info */}
              {analysis && (
                <div className="space-y-1">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase">
                    Spec Version
                  </h3>
                  <p className="text-sm">{analysis.version}</p>
                </div>
              )}

              {/* Focused decision details */}
              {focusedDecision && (
                <div className="space-y-2 pt-4 border-t">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase">
                    Selected Decision
                  </h3>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">{focusedDecision.label}</p>
                    <div className="flex gap-2">
                      <Badge variant="outline">{focusedDecision.type}</Badge>
                      <Badge variant="outline">
                        Importance: {focusedDecision.importance ?? 3}
                      </Badge>
                    </div>
                    {focusedDecision.rationale && (
                      <p className="text-xs text-muted-foreground">
                        {focusedDecision.rationale}
                      </p>
                    )}
                    <div className="pt-2">
                      <h4 className="text-xs font-medium mb-1">Options</h4>
                      <ul className="text-xs space-y-1">
                        {Object.entries(focusedDecision.options).map(
                          ([optId, opt]) => (
                            <li key={optId} className="flex items-center gap-2">
                              <code className="bg-muted px-1 rounded">{optId}</code>
                              <span className="text-muted-foreground">
                                {opt.label}
                              </span>
                              {focusedDecision.default === optId && (
                                <Badge variant="secondary" className="text-[10px] h-4">
                                  default
                                </Badge>
                              )}
                            </li>
                          )
                        )}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}
