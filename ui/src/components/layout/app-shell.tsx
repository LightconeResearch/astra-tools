"use client";

import { NavigatorPane } from "./navigator-pane";
import { DocumentCanvas } from "./document-canvas";
import { InspectorPane } from "./inspector-pane";

export function AppShell() {
  return (
    <div className="h-screen w-screen flex flex-col bg-background overflow-hidden">
      {/* Header */}
      <header className="h-12 border-b flex items-center px-4 shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-lg">ASP</span>
          <span className="text-muted-foreground text-sm">
            Agentic Science Protocol
          </span>
        </div>
      </header>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Navigator Pane */}
        <aside className="w-64 shrink-0 border-r bg-muted/30 overflow-hidden">
          <NavigatorPane />
        </aside>

        {/* Document Canvas */}
        <main className="flex-1 overflow-hidden">
          <DocumentCanvas />
        </main>

        {/* Inspector Pane */}
        <aside className="w-72 shrink-0 border-l bg-muted/30 overflow-hidden">
          <InspectorPane />
        </aside>
      </div>
    </div>
  );
}
