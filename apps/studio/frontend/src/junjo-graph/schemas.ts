import { z } from 'zod'

export const JNodeSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: z.string(),
  // For RunConcurrent nodes
  isSubgraph: z.boolean().optional(),
  children: z.array(z.string()).optional(),
  // New properties for Subflow nodes
  isSubflow: z.boolean().optional(),
  subflowSourceId: z.string().optional(),
  subflowSinkId: z.string().optional(),
})
export type JNode = z.infer<typeof JNodeSchema>

export const JEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  condition: z.string().nullable(),
  // Updated to support edge types
  type: z.enum(['explicit', 'subflow']).optional().default('explicit'),
  // New property for Subflow edges
  subflowId: z.string().nullable().optional(),
})
export type JEdge = z.infer<typeof JEdgeSchema>

export const JGraphSchema = z.object({
  v: z.number(),
  nodes: z.array(JNodeSchema),
  edges: z.array(JEdgeSchema),
})
export type JGraph = z.infer<typeof JGraphSchema>
