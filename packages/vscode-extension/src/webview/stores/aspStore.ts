import { create } from 'zustand';
import type { AnalysisSpec, Constraint, ValidationError } from '../../types/asp';

// Type for the VSCode API
declare const acquireVsCodeApi: () => {
  postMessage: (message: unknown) => void;
  getState: () => unknown;
  setState: (state: unknown) => void;
};

interface Selection {
  type: 'decision' | 'option' | 'input' | 'output';
  decisionId?: string;
  optionId?: string;
  inputId?: string;
  outputId?: string;
}

interface AspState {
  // Data
  analysis: AnalysisSpec | null;
  constraints: Constraint[];
  errors: ValidationError[];
  filePath: string | null;

  // UI state
  selection: Selection | null;
  expandedDecisions: Set<string>;
  editingField: string | null;

  // Universe builder state
  currentSelections: Record<string, string>;
  validOptions: Record<string, Record<string, { valid: boolean; reason?: string }>>;
  universes: { name: string; selections: Record<string, string> }[];

  // Actions
  setAnalysis: (analysis: AnalysisSpec | null, errors: ValidationError[], filePath: string | null) => void;
  setConstraints: (constraints: Constraint[]) => void;
  setSelection: (selection: Selection | null) => void;
  toggleExpanded: (decisionId: string) => void;
  setEditingField: (field: string | null) => void;
  setCurrentSelections: (selections: Record<string, string>) => void;
  updateSelection: (decisionId: string, optionId: string) => void;
  setValidOptions: (decisionId: string, options: Record<string, { valid: boolean; reason?: string }>) => void;
  setUniverses: (universes: { name: string; selections: Record<string, string> }[]) => void;

  // VSCode communication
  vscode: ReturnType<typeof acquireVsCodeApi> | null;
  sendMessage: (message: unknown) => void;
}

export const useAspStore = create<AspState>((set, get) => ({
  // Initial state
  analysis: null,
  constraints: [],
  errors: [],
  filePath: null,
  selection: null,
  expandedDecisions: new Set(),
  editingField: null,
  currentSelections: {},
  validOptions: {},
  universes: [],

  // Get VSCode API
  vscode: typeof acquireVsCodeApi !== 'undefined' ? acquireVsCodeApi() : null,

  // Actions
  setAnalysis: (analysis, errors, filePath) => {
    set({ analysis, errors, filePath });

    // Initialize selections with defaults
    if (analysis?.decisions) {
      const selections: Record<string, string> = {};
      for (const [id, decision] of Object.entries(analysis.decisions)) {
        if (decision.default) {
          selections[id] = decision.default;
        } else {
          const firstOption = Object.keys(decision.options)[0];
          if (firstOption) {
            selections[id] = firstOption;
          }
        }
      }
      set({ currentSelections: selections });
    }
  },

  setConstraints: (constraints) => set({ constraints }),

  setSelection: (selection) => {
    set({ selection });

    // Notify VSCode extension of selection change
    const { vscode } = get();
    if (vscode && selection) {
      vscode.postMessage({
        type: 'selectElement',
        element: selection,
      });
    }
  },

  toggleExpanded: (decisionId) =>
    set((state) => {
      const expanded = new Set(state.expandedDecisions);
      if (expanded.has(decisionId)) {
        expanded.delete(decisionId);
      } else {
        expanded.add(decisionId);
      }
      return { expandedDecisions: expanded };
    }),

  setEditingField: (field) => set({ editingField: field }),

  setCurrentSelections: (selections) => set({ currentSelections: selections }),

  updateSelection: (decisionId, optionId) =>
    set((state) => ({
      currentSelections: {
        ...state.currentSelections,
        [decisionId]: optionId,
      },
    })),

  setValidOptions: (decisionId, options) =>
    set((state) => ({
      validOptions: {
        ...state.validOptions,
        [decisionId]: options,
      },
    })),

  setUniverses: (universes) => set({ universes }),

  sendMessage: (message) => {
    const { vscode } = get();
    if (vscode) {
      vscode.postMessage(message);
    }
  },
}));

// Set up message listener
if (typeof window !== 'undefined') {
  window.addEventListener('message', (event) => {
    const message = event.data;
    const store = useAspStore.getState();

    switch (message.type) {
      case 'analysisLoaded':
        store.setAnalysis(message.data, message.errors || [], message.filePath);
        if (message.constraints) {
          store.setConstraints(message.constraints);
        }
        if (message.universes) {
          store.setUniverses(message.universes);
        }
        break;

      case 'validOptions':
        store.setValidOptions(message.decisionId, message.options);
        break;

      case 'validationResult':
        // Handle validation result
        break;
    }
  });

  // Notify extension that webview is ready
  const vscode = useAspStore.getState().vscode;
  if (vscode) {
    vscode.postMessage({ type: 'ready' });
  }
}
