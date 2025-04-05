import { z } from 'zod'

export const JNodeSchema = z.object({
  id: z.string(),
  type: z.string(),
  label: z.string(),
  isSubgraph: z.boolean().optional(),
  children: z.array(z.string()).optional(),
})
export type JNode = z.infer<typeof JNodeSchema>

export const JEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  condition: z.string().nullable(),
  type: z.string().optional(),
})
export type JEdge = z.infer<typeof JEdgeSchema>

export const JGraphSchema = z.object({
  v: z.number(),
  nodes: z.array(JNodeSchema),
  edges: z.array(JEdgeSchema),
})
export type JGraph = z.infer<typeof JGraphSchema>
