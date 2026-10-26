import { defineConfig } from '@playwright/test'

// Test mode: the static site served as-is from this checkout. No keys, no backend, nothing live.
const PORT = 4317

export default defineConfig({
  testDir: 'e2e',
  workers: 1,
  timeout: 120_000,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  webServer: {
    command: `python3 -m http.server ${PORT} --bind 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/jobs-in-germany/`,
    reuseExistingServer: false,
    timeout: 30_000,
    stdout: 'ignore',
    stderr: 'ignore',
  },
})
