// Define Mermaid direction type (adjust if ReactFlowGraphDirection is different)
export type MermaidGraphDirection = 'TB' | 'TD' | 'BT' | 'RL' | 'LR'

// Helper function to escape Mermaid label strings
// Mermaid labels use quotes, so we need to escape internal quotes and backslashes.
export function escapeMermaidLabel(label: string): string {
  // Replace backslashes first, then quotes
  const escaped = label.replace(/\\/g, '\\\\').replace(/"/g, '&quot;')
  return `"${escaped}"` // Enclose in quotes
}
