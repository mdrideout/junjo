// Helper function to extract the rendered graph node ID from a Mermaid element ID.
export const extractGraphNodeIdFromMermaidElementId = (
  svgId: string | null | undefined,
): string | null => {
  if (!svgId) return null
  const prefix = 'flowchart-'
  if (!svgId.startsWith(prefix)) return null

  let nodeId = svgId.substring(prefix.length)
  nodeId = nodeId.replace(/-\d+$/, '')
  return nodeId
}
