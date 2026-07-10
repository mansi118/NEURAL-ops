/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MATRIX_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
