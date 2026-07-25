/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENABLE_FAKE_SMS_DEV_PAGE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
