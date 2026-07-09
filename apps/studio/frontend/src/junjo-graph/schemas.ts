import { z } from 'zod'

export const JNodeSchema = z.object({
  nodeRuntimeId: z.string(),
  nodeStructuralId: z.string(),
  nodeType: z.string(),
  nodeLabel: z.string(),
  isConcurrentSubgraph: z.boolean().optional(),
  childNodeRuntimeIds: z.array(z.string()).optional(),
  isSubflow: z.boolean().optional(),
  subflowGraphStructuralId: z.string().optional(),
  subflowSourceNodeRuntimeId: z.string().optional(),
  subflowSourceNodeStructuralId: z.string().optional(),
  subflowSinkNodeRuntimeIds: z.array(z.string()).optional(),
  subflowSinkNodeStructuralIds: z.array(z.string()).optional(),
})
export type JNode = z.infer<typeof JNodeSchema>

export const JEdgeSchema = z.object({
  edgeStructuralId: z.string(),
  tailNodeRuntimeId: z.string(),
  tailNodeStructuralId: z.string(),
  headNodeRuntimeId: z.string(),
  headNodeStructuralId: z.string(),
  edgeConditionLabel: z.string().nullable(),
  edgeScope: z.enum(['explicit', 'subflow']),
  parentSubflowRuntimeId: z.string().nullable(),
})
export type JEdge = z.infer<typeof JEdgeSchema>

export const JGraphSchema = z.object({
  v: z.number(),
  graphStructuralId: z.string(),
  nodes: z.array(JNodeSchema),
  edges: z.array(JEdgeSchema),
})
export type JGraph = z.infer<typeof JGraphSchema>
