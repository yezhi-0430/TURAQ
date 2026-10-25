import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [{
    name: 'bundle-workspace-scripts',
    apply: 'build',
    transformIndexHtml: {
      order: 'pre',
      handler: html => html.replace(
        /<script src="(\.\/(?:api|auth|admin|actions|entrance|market-chart|market-detail|market|watchlist|stock-search|risk|risk-auto|paper-trading|theme-ui|markdown|conversation|context-memory|settings)\.js)" defer><\/script>/g,
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
