# ASP Claude Code Plugins

This directory contains Claude Code plugins for working with ASP (Agentic Science Protocol).

## Available Plugins

### asp-analysis

Work with ASP analyses - create specs, extract insights, validate, and manage universes.

**Skills provided:**
- `asp-analysis`: Help design and execute ASP analyses

## Plugin Installation

When you run `asp init` to create a new analysis project, Claude Code is automatically configured to install the ASP plugin. Just run `claude` in your project directory and the plugin will be available.

## Manual Installation

To manually install the plugin in any project, add this to your `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "asp-plugins": {
      "source": {
        "source": "github",
        "repo": "LightconeResearch/ASP"
      }
    }
  },
  "enabledPlugins": {
    "asp-analysis@asp-plugins": true
  }
}
```

## Plugin Development

The marketplace is defined in `/.claude-plugin/marketplace.json` at the repository root. Each plugin has its own directory under `agent-plugins/` with:

- `.claude-plugin/plugin.json` - Plugin manifest
- `skills/` - Skill definitions (markdown files with frontmatter)
