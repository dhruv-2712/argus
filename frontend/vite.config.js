import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Guarantee a single React instance across all chunks. Without this, manual
  // chunking can duplicate React into the charts/maplibre chunks, and a
  // lazy-loaded component (Map) then runs against a React whose hook
  // dispatcher is null — surfacing as "Invalid hook call" (React #321) only
  // in production.
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          // Keep React (and its scheduler) in ONE vendor chunk that every
          // other chunk imports from — never duplicated.
          if (
            id.includes('node_modules/react/') ||
            id.includes('node_modules/react-dom/') ||
            id.includes('node_modules/scheduler/')
          ) {
            return 'react-vendor'
          }
          if (id.includes('maplibre-gl')) return 'maplibre'
          if (id.includes('recharts') || id.includes('/d3-') || id.includes('victory-vendor')) {
            return 'charts'
          }
        },
      },
    },
  },
})
