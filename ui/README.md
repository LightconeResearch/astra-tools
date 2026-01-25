# ASP Web UI

A web-based UI for interacting with ASP (Agentic Science Protocol) analysis specifications.

## Technology Stack

- **Frontend**: Next.js 14+ with App Router
- **UI Components**: shadcn/ui + Radix UI
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Backend**: FastAPI (in `../backend/`)

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+ (for the backend)

### Development

1. **Start the backend server:**

```bash
cd ../backend
pip install -r requirements.txt
ASP_WORK_DIR=/path/to/your/analysis uvicorn main:app --reload
```

2. **Start the frontend:**

```bash
npm install
npm run dev
```

3. Open http://localhost:3000

### Environment Variables

Create a `.env.local` file:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Features

### Three-Pane Layout

- **Navigator** (left): Table of contents, LOD slider, type filters
- **Canvas** (center): Analysis content with editable decisions
- **Inspector** (right): Validation results, details

### LOD (Level of Detail) Slider

Filter decisions by importance level (1-5):
- 1: Critical decisions only
- 5: All decisions (including implementation details)

### Inline Editing

Click on rationale or descriptions to edit them inline. Changes are:
1. Validated instantly (client-side schema validation)
2. Sent to server for semantic validation
3. Auto-saved with debouncing

### MCP Integration

The UI exposes context to external AI agents via MCP (Model Context Protocol):

- `GET /api/mcp/context` - Current UI state
- `PUT /api/mcp/context` - Update from frontend
- `POST /api/mcp/resource` - Get specific resources
- `POST /api/mcp/tool` - Call tools (edit proposals)

## Project Structure

```
ui/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── layout/             # App shell, panes
│   │   ├── canvas/             # Decision panel, editable text
│   │   ├── navigator/          # TOC, filters
│   │   └── ui/                 # shadcn/ui components
│   └── lib/
│       ├── stores/             # Zustand stores
│       ├── api/                # API client
│       ├── hooks/              # React hooks
│       ├── mcp/                # MCP context
│       └── types/              # TypeScript types
├── package.json
└── tailwind.config.ts
```

## Building

```bash
npm run build
npm run start
```

## Development Commands

```bash
# Lint
npm run lint

# Type check
npx tsc --noEmit
```
