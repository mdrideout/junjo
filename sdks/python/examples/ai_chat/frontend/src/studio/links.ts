import type { PublicConfig } from '../api/schemas'

export type ResolvableExecutableType = 'workflow' | 'agent'

export function studioResolutionUrl(
  config: PublicConfig,
  executableType: ResolvableExecutableType,
  runtimeId: string,
  destination: 'detail' | 'trace' = 'detail',
): string | null {
  if (!config.debug_enabled || config.studio_ui_url === null) return null

  const url = new URL('/resolve/executable', config.studio_ui_url)
  url.searchParams.set('service_namespace', config.service_namespace)
  url.searchParams.set('service_name', config.service_name)
  url.searchParams.set('executable_type', executableType)
  url.searchParams.set('runtime_id', runtimeId)
  url.searchParams.set('destination', destination)
  return url.href
}
