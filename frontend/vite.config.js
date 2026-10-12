import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react(), {
    name: 'bundle-workspace-scripts',
    apply: 'build',
    transformIndexHtml: {
      order: 'pre',
      handler: html => html.replace(
        /<script src="(\.\/(?:api|auth|admin|actions|entrance|market-chart|market-detail|market|watchlist|stock-search)\.js)" defer><\/script>/g,
        '<script type="module" src="$1"></script>'
      )
    }
  }],
  server: {
    port: 3000,
    proxy: {
      '^/api/': {
        target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8888',
        changeOrigin: false
      }
    }
  }
})
