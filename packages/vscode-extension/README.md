# ASP VSCode Extension

Visualize and interact with ASP (Agentic Science Protocol) analysis specifications directly in VSCode.

## Features

### Decision Visualization
- **Decision Cards**: Interactive cards showing each decision with options, constraints, and importance levels
- **Inline Editing**: Click any label or description to edit directly in the visualization
- **Constraint Awareness**: Visual indicators for option conflicts and requirements
- **Collapsible Details**: Expand decisions to see descriptions, constraints, and evidence

### Universe Builder
- Build valid universe configurations with constraint-aware dropdowns
- Live validation against all constraints
- Save universes to `universes/*.yaml`

## Installation

```bash
cd packages/vscode-extension
npm install
npm run build
```

Press F5 in VSCode to launch the Extension Development Host.

## Commands

- **ASP: Open Visualization** - Open the decision visualization for asp.yaml
- **ASP: Validate Analysis** - Validate the current asp.yaml file
- **ASP: Open Universe Builder** - Open the universe builder panel

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `asp.autoValidate` | `true` | Validate asp.yaml on save |

## Development

```bash
# Watch mode for development
npm run dev

# Type checking
npm run typecheck

# Linting
npm run lint

# Run tests
npm run test

# Package extension
npm run package
```

## Architecture

```
src/
├── extension.ts          # Entry point
├── panels/               # Webview panels
│   ├── VisualizationPanel.ts
│   └── UniverseBuilderPanel.ts
├── services/             # Core services
│   ├── AspParser.ts      # YAML parsing and validation
│   ├── FileWatcher.ts    # File change detection
│   ├── ConstraintGraph.ts # Constraint analysis
│   └── YamlWriter.ts     # Round-trip YAML editing
├── webview/              # React UI
│   ├── App.tsx           # Main visualization
│   ├── UniverseBuilderApp.tsx
│   ├── ui/               # Reusable UI components
│   │   ├── card.tsx
│   │   ├── badge.tsx
│   │   ├── button.tsx
│   │   ├── checkbox.tsx
│   │   ├── tooltip.tsx
│   │   ├── collapsible.tsx
│   │   └── stars.tsx
│   ├── components/       # Feature components
│   │   ├── DecisionBox.tsx
│   │   ├── OptionCard.tsx
│   │   ├── ConstraintBadge.tsx
│   │   ├── MarkdownEditor.tsx
│   │   └── UniverseBuilder.tsx
│   ├── stores/           # State management (Zustand)
│   └── lib/              # Utilities
└── types/                # TypeScript types
```

## UI Component Library

The extension uses a custom shadcn/ui-inspired component library with VSCode theme integration:

- **Card** - Container with variants (default, elevated, interactive, selected)
- **Badge** - Type indicators with semantic colors (method, parameter, data, warning, error)
- **Button** - Primary, secondary, ghost, and outline variants
- **RadioIndicator/CheckboxIndicator** - Selection indicators with animations
- **Tooltip** - Hover tooltips with positioning options
- **Collapsible** - Animated expand/collapse sections
- **Stars** - Importance rating display

All components use VSCode CSS variables for native theme integration.
