// Helper function to extract the rendered graph node ID from a Mermaid element ID.
export const extractGraphNodeIdFromMermaidElementId = (
  svgId: string | null | undefined,
): string | null => {
  if (!svgId) return null
  const prefix = 'flowchart-'

  let nodeId = svgId.startsWith(prefix) ? svgId.substring(prefix.length) : svgId
  nodeId = nodeId.replace(/-\d+$/, '')
  return nodeId
}
