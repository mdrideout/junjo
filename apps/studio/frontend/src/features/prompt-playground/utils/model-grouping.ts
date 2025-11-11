import type { ModelInfo } from '../fetch/model-discovery'

export interface ParsedModelInfo {
  original: ModelInfo
  productFamily: string // "gemini", "gemma", etc. - PRIMARY grouping
  version: string // "2.5", "2.0", "1.5", etc. - SECONDARY grouping
  variant: string // "flash", "pro", "flash-8b", etc. - the specific model variant
  releaseType: 'stable' | 'preview' | 'exp' // for filtering only
  displayName: string
  sortKey: string // for sorting within groups
  isDated?: boolean // whether this model has a date suffix (for filtering)
}

/**
 * Parse an Anthropic model name into its components
 * Examples:
 * - claude-3-opus-20240229 → { productFamily: "opus", version: "3", variant: "opus", releaseType: "stable" }
 * - claude-3-5-sonnet-20240620 → { productFamily: "sonnet", version: "3.5", variant: "sonnet", releaseType: "stable" }
 * - claude-3-haiku-20240307 → { productFamily: "haiku", version: "3", variant: "haiku", releaseType: "stable" }
 * - claude-sonnet-4-5-20250929 → { productFamily: "sonnet", version: "4.5", variant: "sonnet", releaseType: "stable" }
 */
export function parseAnthropicModel(model: ModelInfo): ParsedModelInfo {
  const id = model.id.toLowerCase()

  // All Anthropic models are considered stable
  const releaseType: 'stable' | 'preview' | 'exp' = 'stable'

  // Extract product family (haiku, sonnet, opus)
  let productFamily = 'unknown'
  let variant = 'unknown'

  if (id.includes('haiku')) {
    productFamily = 'haiku'
    variant = 'haiku'
  } else if (id.includes('sonnet')) {
    productFamily = 'sonnet'
    variant = 'sonnet'
  } else if (id.includes('opus')) {
    productFamily = 'opus'
    variant = 'opus'
  }

  // Extract version - handle both patterns:
  // claude-3-opus-... (version 3)
  // claude-3-5-sonnet-... (version 3.5)
  // claude-sonnet-4-5-... (version 4.5)
  let version = '0.0'

  // Try pattern: claude-X-Y-family or claude-family-X-Y
  const versionMatch1 = id.match(/claude-(\d+)-(\d+)/)
  const versionMatch2 = id.match(/claude-(?:haiku|sonnet|opus)-(\d+)-(\d+)/)

  if (versionMatch1) {
    const [, major, minor] = versionMatch1
    version = minor === '0' ? major : `${major}.${minor}`
  } else if (versionMatch2) {
    const [, major, minor] = versionMatch2
    version = minor === '0' ? major : `${major}.${minor}`
  } else {
    // Try single version number: claude-X-family
    const singleVersionMatch = id.match(/claude-(\d+)-/)
    if (singleVersionMatch) {
      version = singleVersionMatch[1]
    }
  }

  // Create display name - capitalize the product family
  const displayName = productFamily.charAt(0).toUpperCase() + productFamily.slice(1)

  // Create sort key: version (descending), then product family
  // Product family order: opus (highest tier) > sonnet > haiku
  const familyOrder = productFamily === 'opus' ? 0 : productFamily === 'sonnet' ? 1 : productFamily === 'haiku' ? 2 : 3
  const sortKey = `${version}-${familyOrder}`

  return {
    original: model,
    productFamily,
    version,
    variant,
    releaseType,
    displayName,
    sortKey,
  }
}

/**
 * Parse an OpenAI model name into its components
 * Examples:
 * - gpt-5-pro → { productFamily: "gpt-5", version: "5", variant: "pro", releaseType: "stable" }
 * - gpt-4o-mini-2024-07-18 → { productFamily: "gpt-4o", version: "4.0", variant: "mini", releaseType: "stable" }
 * - gpt-4o-audio-preview → { productFamily: "gpt-4o", version: "4.0", variant: "audio", releaseType: "preview" }
 * - gpt-realtime-mini → { productFamily: "specialized", version: "0", variant: "realtime-mini", releaseType: "stable" }
 */
export function parseOpenAIModel(model: ModelInfo): ParsedModelInfo {
  const id = model.id.toLowerCase()

  // Strip provider prefix (e.g., "openai/")
  const idWithoutProvider = id.includes('/') ? id.split('/')[1] : id

  // Determine release type
  let releaseType: 'stable' | 'preview' | 'exp' = 'stable'
  if (idWithoutProvider.includes('-preview')) {
    releaseType = 'preview'
  }

  // Extract product family and variant
  let productFamily = 'unknown'
  let version = '0'
  let variant = 'standard'

  // o4 family (reasoning models)
  if (idWithoutProvider.startsWith('o4-')) {
    productFamily = 'o4'
    version = 'o4'

    if (idWithoutProvider.includes('-mini')) {
      variant = 'mini'
    } else if (idWithoutProvider.includes('-deep-research')) {
      variant = 'deep-research'
    } else {
      variant = 'standard'
    }
  }
  // o3 family (reasoning models)
  else if (idWithoutProvider.startsWith('o3-') || idWithoutProvider === 'o3') {
    productFamily = 'o3'
    version = 'o3'

    if (idWithoutProvider.includes('-mini')) {
      variant = 'mini'
    } else if (idWithoutProvider.includes('-pro')) {
      variant = 'pro'
    } else if (idWithoutProvider.includes('-deep-research')) {
      variant = 'deep-research'
    } else {
      variant = 'standard'
    }
  }
  // o1 family (reasoning models)
  else if (idWithoutProvider.startsWith('o1-') || idWithoutProvider === 'o1') {
    productFamily = 'o1'
    version = 'o1'

    if (idWithoutProvider.includes('-mini')) {
      variant = 'mini'
    } else if (idWithoutProvider.includes('-pro')) {
      variant = 'pro'
    } else {
      variant = 'standard'
    }
  }
  // GPT-5 family
  else if (idWithoutProvider.startsWith('gpt-5')) {
    productFamily = 'gpt-5'
    version = '5'

    if (idWithoutProvider.includes('-pro')) {
      variant = 'pro'
    } else if (idWithoutProvider.includes('-mini')) {
      variant = 'mini'
    } else if (idWithoutProvider.includes('-nano')) {
      variant = 'nano'
    } else if (idWithoutProvider.includes('-search-api')) {
      variant = 'search-api'
    } else if (idWithoutProvider.includes('-chat-latest')) {
      variant = 'chat-latest'
    } else if (idWithoutProvider.includes('-codex')) {
      variant = 'codex'
    } else {
      variant = 'standard'
    }
  }
  // GPT-4.1 family
  else if (idWithoutProvider.startsWith('gpt-4.1')) {
    productFamily = 'gpt-4.1'
    version = '4.1'

    if (idWithoutProvider.includes('-mini')) {
      variant = 'mini'
    } else if (idWithoutProvider.includes('-nano')) {
      variant = 'nano'
    } else {
      variant = 'standard'
    }
  }
  // GPT-4o family
  else if (idWithoutProvider.startsWith('gpt-4o')) {
    productFamily = 'gpt-4o'
    version = '4.0'

    if (idWithoutProvider.includes('-mini')) {
      variant = 'mini'
    } else if (idWithoutProvider.includes('-audio')) {
      variant = 'audio'
    } else if (idWithoutProvider.includes('-realtime')) {
      variant = 'realtime'
    } else if (idWithoutProvider.includes('-search')) {
      variant = 'search'
    } else if (idWithoutProvider.includes('-transcribe')) {
      variant = 'transcribe'
    } else if (idWithoutProvider.includes('-tts')) {
      variant = 'tts'
    } else {
      variant = 'standard'
    }
  }
  // GPT-4 family (non-4o)
  else if (idWithoutProvider.startsWith('gpt-4')) {
    productFamily = 'gpt-4'
    version = '4'

    if (idWithoutProvider.includes('-turbo')) {
      variant = 'turbo'
    } else {
      variant = 'standard'
    }
  }
  // GPT-3.5 family
  else if (idWithoutProvider.startsWith('gpt-3.5')) {
    productFamily = 'gpt-3.5'
    version = '3.5'

    if (idWithoutProvider.includes('-turbo-instruct')) {
      variant = 'turbo-instruct'
    } else if (idWithoutProvider.includes('-turbo')) {
      variant = 'turbo'
    } else if (idWithoutProvider.includes('-instruct')) {
      variant = 'instruct'
    } else {
      variant = 'standard'
    }
  }
  // Specialized models (realtime, audio, image without version prefix)
  else if (idWithoutProvider.startsWith('gpt-realtime')) {
    productFamily = 'specialized'
    version = '0'
    variant = 'realtime'
  } else if (idWithoutProvider.startsWith('gpt-audio')) {
    productFamily = 'specialized'
    version = '0'
    variant = 'audio'
  } else if (idWithoutProvider.startsWith('gpt-image')) {
    productFamily = 'specialized'
    version = '0'
    variant = 'image'
  }

  // Create display name - use the model's display_name or the full ID (without provider prefix)
  let displayName = model.display_name || idWithoutProvider

  // Detect dated models (models with date suffixes like -YYYY-MM-DD or -MMDD)
  const hasDate = /\d{4}-\d{2}-\d{2}/.test(idWithoutProvider) || /-\d{4}$/.test(idWithoutProvider)

  // Create sort key: prioritize non-dated aliases, then sort by date descending
  const releaseTypeOrder = releaseType === 'stable' ? 0 : releaseType === 'preview' ? 1 : 2
  const aliasOrder = hasDate ? 1 : 0 // Non-dated aliases come first
  const sortKey = `${variant}-${aliasOrder}-${releaseTypeOrder}-${idWithoutProvider}`

  return {
    original: model,
    productFamily,
    version,
    variant,
    releaseType,
    displayName,
    sortKey,
    isDated: hasDate,
  }
}

/**
 * Parse a Gemini/Gemma model name into its components
 * Examples:
 * - gemini-2.5-flash-exp → { productFamily: "gemini", version: "2.5", variant: "flash", releaseType: "exp" }
 * - gemini-2.0-flash-preview-06-17 → { productFamily: "gemini", version: "2.0", variant: "flash", releaseType: "preview" }
 * - gemini-1.5-pro → { productFamily: "gemini", version: "1.5", variant: "pro", releaseType: "stable" }
 * - gemma-2-9b-it → { productFamily: "gemma", version: "2", variant: "9b-it", releaseType: "stable" }
 */
export function parseGeminiModel(model: ModelInfo): ParsedModelInfo {
  const id = model.id.toLowerCase()

  // Strip provider prefix (e.g., "gemini/" or "google/")
  const idWithoutProvider = id.includes('/') ? id.split('/')[1] : id

  // Extract release type
  let releaseType: 'stable' | 'preview' | 'exp' = 'stable'
  if (idWithoutProvider.includes('-exp')) {
    releaseType = 'exp'
  } else if (idWithoutProvider.includes('-preview')) {
    releaseType = 'preview'
  }

  // Extract product family (gemini, gemma, etc.) - first segment
  const parts = idWithoutProvider.split('-')
  const productFamily = parts[0] // "gemini" or "gemma"

  // Extract version (e.g., "2.5", "2.0", "1.5", or "latest")
  // Check for "-latest" in the model name first
  let version: string
  if (idWithoutProvider.includes('-latest')) {
    version = 'latest'
  } else {
    const versionMatch = idWithoutProvider.match(/^(?:gemini|gemma)-(\d+(?:\.\d+)?)/)
    version = versionMatch ? versionMatch[1] : '0.0'
  }

  // Extract variant (everything between version and release type suffixes)
  let variant = 'unknown'
  const withoutFamily = idWithoutProvider.replace(`${productFamily}-`, '')
  const withoutVersion = withoutFamily.replace(`${version}-`, '')

  // Remove release type suffixes and date suffixes
  let cleanVariant = withoutVersion
    .replace(/-exp$/i, '')
    .replace(/-preview.*$/i, '')

  // The remaining is the variant
  variant = cleanVariant || 'base'

  // Create display name (just the variant name, capitalized)
  const displayName = variant.split('-').map(part =>
    part.charAt(0).toUpperCase() + part.slice(1)
  ).join(' ')

  // Create sort key: variant name, then release type (stable first)
  const releaseTypeOrder = releaseType === 'stable' ? 0 : releaseType === 'preview' ? 1 : 2
  const sortKey = `${variant}-${releaseTypeOrder}`

  return {
    original: model,
    productFamily,
    version,
    variant,
    releaseType,
    displayName,
    sortKey,
  }
}

/**
 * Group models hierarchically: Product Family > Version > Release Type > Variants
 */
export interface ReleaseTypeGroup {
  releaseType: 'stable' | 'preview' | 'exp'
  displayName: string
  models: ParsedModelInfo[]
}

export interface VersionGroup {
  version: string
  releaseTypeGroups: ReleaseTypeGroup[]
}

export interface ProductFamilyGroup {
  productFamily: string
  displayName: string
  versionGroups: VersionGroup[]
}

export function groupGeminiModels(models: ModelInfo[]): ProductFamilyGroup[] {
  // Parse all models
  const parsed = models.map(parseGeminiModel)

  // Group by product family first
  const familyMap = new Map<string, ParsedModelInfo[]>()
  for (const model of parsed) {
    if (!familyMap.has(model.productFamily)) {
      familyMap.set(model.productFamily, [])
    }
    familyMap.get(model.productFamily)!.push(model)
  }

  // Build hierarchical structure
  const result: ProductFamilyGroup[] = []
  for (const [productFamily, familyModels] of familyMap) {
    // Group by version within this family
    const versionMap = new Map<string, ParsedModelInfo[]>()
    for (const model of familyModels) {
      if (!versionMap.has(model.version)) {
        versionMap.set(model.version, [])
      }
      versionMap.get(model.version)!.push(model)
    }

    // Build version groups with release type sub-groups
    const versionGroups: VersionGroup[] = []
    for (const [version, versionModels] of versionMap) {
      // Group by release type within this version
      const releaseTypeMap = new Map<'stable' | 'preview' | 'exp', ParsedModelInfo[]>()
      for (const model of versionModels) {
        if (!releaseTypeMap.has(model.releaseType)) {
          releaseTypeMap.set(model.releaseType, [])
        }
        releaseTypeMap.get(model.releaseType)!.push(model)
      }

      // Sort models within each release type by sortKey
      const releaseTypeGroups: ReleaseTypeGroup[] = []
      for (const [releaseType, releaseTypeModels] of releaseTypeMap) {
        releaseTypeModels.sort((a, b) => a.sortKey.localeCompare(b.sortKey))

        const displayName = releaseType === 'stable' ? 'Stable' :
                           releaseType === 'preview' ? 'Preview' :
                           'Experimental'

        releaseTypeGroups.push({
          releaseType,
          displayName,
          models: releaseTypeModels
        })
      }

      // Sort release type groups: stable first, then preview, then exp
      releaseTypeGroups.sort((a, b) => {
        const order = { stable: 0, preview: 1, exp: 2 }
        return order[a.releaseType] - order[b.releaseType]
      })

      versionGroups.push({ version, releaseTypeGroups })
    }

    // Sort version groups: "latest" first, then by version number descending (newest first)
    versionGroups.sort((a, b) => {
      // "latest" always comes first
      if (a.version === 'latest') return -1
      if (b.version === 'latest') return 1

      // Otherwise sort by version number descending
      const aNum = parseFloat(a.version)
      const bNum = parseFloat(b.version)
      return bNum - aNum // Descending order
    })

    result.push({
      productFamily,
      displayName: productFamily.charAt(0).toUpperCase() + productFamily.slice(1),
      versionGroups,
    })
  }

  // Sort product families alphabetically
  result.sort((a, b) => a.productFamily.localeCompare(b.productFamily))

  return result
}

/**
 * Group Anthropic models by Product Family (Haiku/Sonnet/Opus) with simple flat structure
 */
export function groupAnthropicModels(models: ModelInfo[]): ProductFamilyGroup[] {
  // Parse all models
  const parsed = models.map(parseAnthropicModel)

  // Group by product family (haiku, sonnet, opus)
  const familyMap = new Map<string, ParsedModelInfo[]>()
  for (const model of parsed) {
    if (!familyMap.has(model.productFamily)) {
      familyMap.set(model.productFamily, [])
    }
    familyMap.get(model.productFamily)!.push(model)
  }

  // Build simple structure: Product Family > Models (no version subgroups)
  const result: ProductFamilyGroup[] = []
  for (const [productFamily, familyModels] of familyMap) {
    // Sort models by version descending (newest first), then by model ID
    familyModels.sort((a, b) => {
      const versionCompare = parseFloat(b.version) - parseFloat(a.version)
      if (versionCompare !== 0) return versionCompare
      return a.original.id.localeCompare(b.original.id)
    })

    // Create a single version group with all models
    const versionGroups: VersionGroup[] = [
      {
        version: '', // No version header needed
        releaseTypeGroups: [
          {
            releaseType: 'stable',
            displayName: 'Stable',
            models: familyModels
          }
        ]
      }
    ]

    result.push({
      productFamily,
      displayName: productFamily.charAt(0).toUpperCase() + productFamily.slice(1),
      versionGroups,
    })
  }

  // Sort product families by tier: Opus > Sonnet > Haiku
  result.sort((a, b) => {
    const order = { opus: 0, sonnet: 1, haiku: 2 }
    const aOrder = order[a.productFamily as keyof typeof order] ?? 99
    const bOrder = order[b.productFamily as keyof typeof order] ?? 99
    return aOrder - bOrder
  })

  return result
}

/**
 * Group OpenAI models by Product Family with variant subgroups
 * Structure: GPT-5 > Pro/Standard/Mini/Nano/etc. > Stable/Preview
 */
export function groupOpenAIModels(models: ModelInfo[]): ProductFamilyGroup[] {
  // Parse all models
  const parsed = models.map(parseOpenAIModel)

  // Group by product family
  const familyMap = new Map<string, ParsedModelInfo[]>()
  for (const model of parsed) {
    if (!familyMap.has(model.productFamily)) {
      familyMap.set(model.productFamily, [])
    }
    familyMap.get(model.productFamily)!.push(model)
  }

  // Build hierarchical structure
  const result: ProductFamilyGroup[] = []
  for (const [productFamily, familyModels] of familyMap) {
    // Group by variant within this family
    const variantMap = new Map<string, ParsedModelInfo[]>()
    for (const model of familyModels) {
      if (!variantMap.has(model.variant)) {
        variantMap.set(model.variant, [])
      }
      variantMap.get(model.variant)!.push(model)
    }

    // Build variant groups with release type sub-groups
    const versionGroups: VersionGroup[] = []
    for (const [variant, variantModels] of variantMap) {
      // Group by release type within this variant
      const releaseTypeMap = new Map<'stable' | 'preview' | 'exp', ParsedModelInfo[]>()
      for (const model of variantModels) {
        if (!releaseTypeMap.has(model.releaseType)) {
          releaseTypeMap.set(model.releaseType, [])
        }
        releaseTypeMap.get(model.releaseType)!.push(model)
      }

      // Sort models within each release type by sortKey
      const releaseTypeGroups: ReleaseTypeGroup[] = []
      for (const [releaseType, releaseTypeModels] of releaseTypeMap) {
        releaseTypeModels.sort((a, b) => a.sortKey.localeCompare(b.sortKey))

        const displayName = releaseType === 'stable' ? 'Stable' :
                           releaseType === 'preview' ? 'Preview' :
                           'Experimental'

        releaseTypeGroups.push({
          releaseType,
          displayName,
          models: releaseTypeModels
        })
      }

      // Sort release type groups: stable first, then preview, then exp
      releaseTypeGroups.sort((a, b) => {
        const order = { stable: 0, preview: 1, exp: 2 }
        return order[a.releaseType] - order[b.releaseType]
      })

      // Use variant name as the "version" label in the hierarchy
      versionGroups.push({
        version: variant,
        releaseTypeGroups
      })
    }

    // Sort variant groups by priority
    const variantOrder = {
      'pro': 0,
      'standard': 1,
      'mini': 2,
      'nano': 3,
      'turbo': 4,
      'instruct': 5,
      'audio': 10,
      'realtime': 11,
      'search': 12,
      'transcribe': 13,
      'tts': 14,
      'codex': 15,
      'image': 16
    }
    versionGroups.sort((a, b) => {
      const aOrder = variantOrder[a.version as keyof typeof variantOrder] ?? 99
      const bOrder = variantOrder[b.version as keyof typeof variantOrder] ?? 99
      return aOrder - bOrder
    })

    // Create display name for product family
    let displayName = productFamily
    if (productFamily === 'gpt-5') displayName = 'GPT-5'
    else if (productFamily === 'gpt-4.1') displayName = 'GPT-4.1'
    else if (productFamily === 'gpt-4o') displayName = 'GPT-4o'
    else if (productFamily === 'gpt-4') displayName = 'GPT-4'
    else if (productFamily === 'gpt-3.5') displayName = 'GPT-3.5'
    else if (productFamily === 'o4') displayName = 'o4'
    else if (productFamily === 'o3') displayName = 'o3'
    else if (productFamily === 'o1') displayName = 'o1'
    else if (productFamily === 'specialized') displayName = 'Specialized'

    result.push({
      productFamily,
      displayName,
      versionGroups,
    })
  }

  // Sort product families by explicit order: GPT-5, GPT-4.1, GPT-4o, GPT-4, GPT-3.5, o4, o3, o1, specialized
  const familyOrder = {
    'gpt-5': 0,
    'gpt-4.1': 1,
    'gpt-4o': 2,
    'gpt-4': 3,
    'gpt-3.5': 4,
    'o4': 5,
    'o3': 6,
    'o1': 7,
    'specialized': 8
  }
  result.sort((a, b) => {
    const aOrder = familyOrder[a.productFamily as keyof typeof familyOrder] ?? 99
    const bOrder = familyOrder[b.productFamily as keyof typeof familyOrder] ?? 99
    return aOrder - bOrder
  })

  return result
}

/**
 * Filter models by release type and dated status
 */
export function filterModelsByReleaseType(
  groups: ProductFamilyGroup[],
  options: {
    includeStable: boolean
    includePreview: boolean
    includeExp: boolean
    includeDated?: boolean
  }
): ProductFamilyGroup[] {
  return groups
    .map((familyGroup) => ({
      ...familyGroup,
      versionGroups: familyGroup.versionGroups
        .map((versionGroup) => ({
          ...versionGroup,
          releaseTypeGroups: versionGroup.releaseTypeGroups
            .map((releaseTypeGroup) => {
              // Filter by release type
              if (releaseTypeGroup.releaseType === 'stable' && !options.includeStable) return null
              if (releaseTypeGroup.releaseType === 'preview' && !options.includePreview) return null
              if (releaseTypeGroup.releaseType === 'exp' && !options.includeExp) return null

              // Filter by dated status (if includeDated is explicitly set to false)
              const filteredModels = options.includeDated === false
                ? releaseTypeGroup.models.filter(model => !model.isDated)
                : releaseTypeGroup.models

              return filteredModels.length > 0 ? { ...releaseTypeGroup, models: filteredModels } : null
            })
            .filter((group): group is ReleaseTypeGroup => group !== null),
        }))
        .filter((versionGroup) => versionGroup.releaseTypeGroups.length > 0), // Remove empty version groups
    }))
    .filter((familyGroup) => familyGroup.versionGroups.length > 0) // Remove empty family groups
}

/**
 * Organize models into hierarchical groups for display
 * Handles Gemini, Anthropic, OpenAI (with complex grouping) and other providers (simple list)
 */
export function organizeModels(
  models: ModelInfo[],
  provider: string | null,
  filters: { includeStable: boolean; includePreview: boolean; includeExp: boolean; includeDated?: boolean }
): ProductFamilyGroup[] {
  if (provider === 'gemini') {
    const groups = groupGeminiModels(models)
    return filterModelsByReleaseType(groups, filters)
  }

  if (provider === 'anthropic') {
    const groups = groupAnthropicModels(models)
    // Anthropic models are all stable, but we still apply the filter for consistency
    return filterModelsByReleaseType(groups, filters)
  }

  if (provider === 'openai') {
    const groups = groupOpenAIModels(models)
    return filterModelsByReleaseType(groups, filters)
  }

  // For other providers, create a simple single group structure
  return [
    {
      productFamily: provider || 'models',
      displayName: provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : 'Models',
      versionGroups: [
        {
          version: '',
          releaseTypeGroups: [
            {
              releaseType: 'stable' as const,
              displayName: 'Stable',
              models: models.map((model) => ({
                original: model,
                productFamily: provider || 'unknown',
                version: '',
                variant: model.display_name || model.id,
                releaseType: 'stable' as const,
                displayName: model.display_name || model.id,
                sortKey: model.id,
              })),
            },
          ],
        },
      ],
    },
  ]
}
