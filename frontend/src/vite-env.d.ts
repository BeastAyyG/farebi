/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Farebi API. Empty string = same origin (dev proxy). */
  readonly VITE_API_BASE?: string;
  /** "true" serves fixture responses instead of calling the API. */
  readonly VITE_MOCK_API?: string;
  /** Request timeout in milliseconds. Defaults to 30000. */
  readonly VITE_REQUEST_TIMEOUT_MS?: string;
  /** Max upload size in bytes. Defaults to 10485760 (10MB). */
  readonly VITE_MAX_UPLOAD_BYTES?: string;
  /** Max pixel dimension. Defaults to 2048. */
  readonly VITE_MAX_PIXEL_DIM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
