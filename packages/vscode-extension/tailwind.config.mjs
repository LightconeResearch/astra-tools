/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/webview/**/*.{ts,tsx,html}'],
  theme: {
    extend: {
      colors: {
        // Core semantic colors using VSCode CSS variables
        background: 'var(--vscode-editor-background)',
        foreground: 'var(--vscode-editor-foreground)',
        border: 'var(--vscode-panel-border)',
        accent: 'var(--vscode-focusBorder)',
        muted: {
          DEFAULT: 'var(--vscode-descriptionForeground)',
          foreground: 'var(--vscode-descriptionForeground)',
        },

        // Card colors
        card: {
          DEFAULT: 'var(--vscode-editor-background)',
          foreground: 'var(--vscode-editor-foreground)',
          border: 'var(--vscode-panel-border)',
          hover: 'var(--vscode-list-hoverBackground)',
        },

        // Button colors
        primary: {
          DEFAULT: 'var(--vscode-button-background)',
          foreground: 'var(--vscode-button-foreground)',
          hover: 'var(--vscode-button-hoverBackground)',
        },
        secondary: {
          DEFAULT: 'var(--vscode-button-secondaryBackground)',
          foreground: 'var(--vscode-button-secondaryForeground)',
          hover: 'var(--vscode-button-secondaryHoverBackground)',
        },

        // Input colors
        input: {
          DEFAULT: 'var(--vscode-input-background)',
          foreground: 'var(--vscode-input-foreground)',
          border: 'var(--vscode-input-border)',
          placeholder: 'var(--vscode-input-placeholderForeground)',
        },

        // List/selection colors
        list: {
          hover: 'var(--vscode-list-hoverBackground)',
          active: 'var(--vscode-list-activeSelectionBackground)',
          'active-foreground': 'var(--vscode-list-activeSelectionForeground)',
        },

        // Badge/chip colors
        badge: {
          DEFAULT: 'var(--vscode-badge-background)',
          foreground: 'var(--vscode-badge-foreground)',
        },

        // Status colors
        success: 'var(--vscode-terminal-ansiGreen)',
        warning: {
          DEFAULT: 'var(--vscode-editorWarning-foreground)',
          background: 'var(--vscode-inputValidation-warningBackground)',
        },
        error: {
          DEFAULT: 'var(--vscode-editorError-foreground)',
          background: 'var(--vscode-inputValidation-errorBackground)',
        },
        info: {
          DEFAULT: 'var(--vscode-editorInfo-foreground)',
          background: 'var(--vscode-inputValidation-infoBackground)',
        },

        // Chart colors for badges
        chart: {
          purple: 'var(--vscode-charts-purple)',
          blue: 'var(--vscode-charts-blue)',
          green: 'var(--vscode-charts-green)',
          yellow: 'var(--vscode-charts-yellow)',
          orange: 'var(--vscode-charts-orange)',
          red: 'var(--vscode-charts-red)',
        },

        // Tooltip/hover widget
        tooltip: {
          DEFAULT: 'var(--vscode-editorHoverWidget-background)',
          foreground: 'var(--vscode-editorHoverWidget-foreground)',
          border: 'var(--vscode-editorHoverWidget-border)',
        },
      },
      fontFamily: {
        sans: 'var(--vscode-font-family)',
        mono: 'var(--vscode-editor-font-family)',
      },
      fontSize: {
        xs: '11px',
        sm: '12px',
        base: '13px',
        lg: '14px',
        xl: '16px',
        '2xl': '18px',
      },
      borderRadius: {
        DEFAULT: '4px',
        sm: '2px',
        md: '4px',
        lg: '6px',
      },
      boxShadow: {
        card: '0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24)',
        'card-hover': '0 3px 6px rgba(0, 0, 0, 0.15), 0 2px 4px rgba(0, 0, 0, 0.12)',
        tooltip: '0 2px 8px rgba(0, 0, 0, 0.2)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
        fast: '100ms',
        normal: '150ms',
        slow: '200ms',
      },
      animation: {
        'spin-slow': 'spin 1s linear infinite',
        'fade-in': 'fadeIn 150ms ease-out',
        'slide-down': 'slideDown 150ms ease-out',
        'slide-up': 'slideUp 150ms ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
