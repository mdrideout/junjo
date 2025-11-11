// Centralized configuration for the frontend application

declare global {
  interface Window {
    runtimeConfig?: {
      API_HOST?: string
    }
  }
}

export const API_HOST = window.runtimeConfig?.API_HOST || 'http://localhost:1323'

export function getApiHost(_endpoint: string): string {
  return API_HOST
}

console.log('Junjo Frontend API Host:', API_HOST)
