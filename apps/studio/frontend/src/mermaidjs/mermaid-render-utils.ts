// Helper function to extract the base junjo.id attribute from the SVG element ID
export const extractMermaidNodeId = (svgId: string | null | undefined): string | null => {
  if (!svgId) return null
  // Assumes format like 'flowchart-NODEID-INDEX' or 'flowchart-NODEID'
  const prefix = 'flowchart-'
  if (!svgId.startsWith(prefix)) return null // Or return svgId if prefix is not guaranteed

  let nodeId = svgId.substring(prefix.length)

  // Remove potential suffix like -0, -1, -10 etc.
  nodeId = nodeId.replace(/-\d+$/, '')
  return nodeId
}
