"use client";

import { useEffect } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useAnalysisStore } from "@/lib/stores/analysis-store";
import { useAutoSave } from "@/lib/hooks/use-auto-save";
import { useMCPSync } from "@/lib/hooks/use-mcp-sync";
import { api } from "@/lib/api/client";

export default function Home() {
  const { setAnalysis, setFilePath, setUniverses, setLoading, setLoadError } =
    useAnalysisStore();

  // Enable auto-save and validation
  useAutoSave();

  // Sync context to MCP server for agent integration
  useMCPSync();

  useEffect(() => {
    async function loadAnalysis() {
      setLoading(true);
      setLoadError(null);
      try {
        const response = await api.loadAnalysis();
        setAnalysis(response.analysis);
        setFilePath(response.filePath);
        setUniverses(response.universes);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setLoadError(message);
      } finally {
        setLoading(false);
      }
    }

    loadAnalysis();
  }, [setAnalysis, setFilePath, setUniverses, setLoading, setLoadError]);

  return <AppShell />;
}
