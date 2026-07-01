/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TATVA_API_ORIGIN: string
  readonly VITE_TATVA_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
