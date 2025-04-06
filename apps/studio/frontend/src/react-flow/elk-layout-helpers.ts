// Cache canvas context for efficiency - create it only once.
let canvasContext: CanvasRenderingContext2D | null = null

/**
 * Estimates the required width and height for a text label using Canvas.
 * NOTE: This is a basic single-line estimation. More complex logic
 * is needed for automatic word wrapping based on a max width.
 */
export function calculateNodeSize(
  text: string,
  fontStyle: string = '12px sans-serif', // Default font - **MUST MATCH YOUR CSS FONT FOR NODES!**
  paddingX: number = 20, // Total horizontal padding (left + right)
  paddingY: number = 10, // Total vertical padding (top + bottom)
  minWidth: number = 100, // Optional minimum width
  minHeight: number = 40, // Optional minimum height (like defaultNodeHeight)
): { width: number; height: number } {
  // Initialize canvas context if it doesn't exist
  if (!canvasContext) {
    try {
      // Create an off-screen canvas
      const canvas = document.createElement('canvas')
      canvasContext = canvas.getContext('2d')
    } catch (e) {
      console.error('Failed to create canvas context for size calculation:', e)
      // Fallback if canvas context creation fails (e.g., non-browser env)
      return { width: Math.max(175, minWidth), height: Math.max(40, minHeight) }
    }
  }
  // If still null after try-catch, return fallback
  if (!canvasContext) {
    return { width: Math.max(175, minWidth), height: Math.max(40, minHeight) }
  }

  // Set the font style to measure
  canvasContext.font = fontStyle

  // Measure the text width
  const metrics = canvasContext.measureText(text || '') // Use empty string if text is null/undefined
  const textWidth = Math.ceil(metrics.width)

  // Estimate text height (simplified for single line)
  // You might need more sophisticated calculation based on font metrics
  // For common fonts, ascent+descent is roughly font size * 1.2-1.4
  let textHeight = Math.ceil(parseFloat(fontStyle) * 1.4) // Rough estimate
  // Try using font metrics if available
  if (metrics.actualBoundingBoxAscent && metrics.actualBoundingBoxDescent) {
    textHeight = Math.ceil(metrics.actualBoundingBoxAscent + metrics.actualBoundingBoxDescent)
  }

  // Calculate final dimensions including padding and minimums
  const width = Math.max(textWidth + paddingX, minWidth)
  const height = Math.max(textHeight + paddingY, minHeight)

  return { width, height }
}
