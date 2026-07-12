// Centralized configuration for the frontend application

declare global {
  interface Window {
    runtimeConfig?: {
      API_HOST?: string
    }
  }
}

export const API_HOST = window.runtimeConfig?.API_HOST || ''
export const DEFAULT_DEV_API_HOST = 'http://localhost:26154'

export function getApiHost(_endpoint: string): string {
  return API_HOST || DEFAULT_DEV_API_HOST
}

console.log('Junjo Frontend API Host:', getApiHost(''))
