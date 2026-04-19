/// <reference types="vite/client" />

// Typed access to the VITE_* env vars baked into the bundle at build time.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
