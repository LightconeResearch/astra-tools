import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// Build multiple entry points as separate chunks
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist/webview',
    rollupOptions: {
      input: {
        visualization: resolve(__dirname, 'src/webview/index.tsx'),
        universeBuilder: resolve(__dirname, 'src/webview/universe-builder.tsx'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'shared-[hash].js',
        assetFileNames: 'style.css',
      },
    },
    cssCodeSplit: false,
    sourcemap: true,
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
});
