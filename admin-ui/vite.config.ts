import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const DEFAULT_TATVA_API = 'https://devopsapi.withtatva.ai'
const DEFAULT_OMNICHANNEL_API = 'https://omni-1-iltl.onrender.com'

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const adminApiKey = rootEnv.ADMIN_API_KEY || rootEnv.VITE_ADMIN_API_KEY || ''
  const tatvaApiOrigin = (
    rootEnv.TATVA_API_BASE_URL || rootEnv.TATVA_USERS_API_BASE_URL || DEFAULT_TATVA_API
  ).replace(/\/$/, '')
  const tatvaApiBase = rootEnv.VITE_TATVA_API_BASE_URL || '/tatva-api'
  const omnichannelApi = (
    rootEnv.OMNICHANNEL_API_URL
    || rootEnv.VITE_API_URL
    || (mode === 'development' ? 'http://127.0.0.1:8000' : DEFAULT_OMNICHANNEL_API)
  ).replace(/\/$/, '')

  return {
    plugins: [react()],
    base: '/krsna/',
    envDir: path.resolve(__dirname, '..'),
    define: {
      'import.meta.env.VITE_TATVA_API_ORIGIN': JSON.stringify(tatvaApiOrigin),
      'import.meta.env.VITE_TATVA_API_BASE_URL': JSON.stringify(tatvaApiBase),
    },
    server: {
      port: 3000,
      proxy: {
        '/admin': {
          target: omnichannelApi,
          changeOrigin: true,
        },
        '/webhook': {
          target: omnichannelApi,
          changeOrigin: true,
        },
        '/media': {
          target: omnichannelApi,
          changeOrigin: true,
        },
        '/tatva-api': {
          target: tatvaApiOrigin,
          changeOrigin: true,
          secure: true,
          rewrite: reqPath => reqPath.replace(/^\/tatva-api/, ''),
          configure: proxy => {
            proxy.on('proxyReq', (proxyReq, req) => {
              const url = String(req.url || '')
              // Auth endpoints: do not attach local panel Bearer or X-Admin-Key
              const isAuthPath = /\/employees\/auth\//.test(url)
              if (!isAuthPath && adminApiKey) {
                proxyReq.setHeader('X-Admin-Key', adminApiKey)
              }
              if (!isAuthPath) {
                const auth = req.headers.authorization
                if (auth) {
                  proxyReq.setHeader('Authorization', auth)
                }
              } else {
                proxyReq.removeHeader('Authorization')
                proxyReq.removeHeader('X-Admin-Key')
              }
            })
            proxy.on('error', (err, _req, res) => {
              console.error('[tatva-api proxy]', err.message)
              if (res && !res.headersSent) {
                res.writeHead(502, { 'Content-Type': 'application/json' })
                res.end(JSON.stringify({
                  success: false,
                  message: `Tatva proxy error: ${err.message}`,
                }))
              }
            })
          },
        },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
    },
  }
})
