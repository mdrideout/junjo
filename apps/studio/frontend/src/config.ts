// This file provides a centralized configuration for the frontend application.

// The API_HOST is determined by checking for a runtime configuration object
// injected by the `prod-startup.sh` script in the production Docker container.
// If the runtime configuration is not found, it defaults to the local
// development server.

declare global {
  interface Window {
    runtimeConfig?: {
      API_HOST?: string
    }
  }
}

export const API_HOST = window.runtimeConfig?.API_HOST || 'http://localhost:1323'

console.log('Junjo Frontend API Host:', API_HOST)
