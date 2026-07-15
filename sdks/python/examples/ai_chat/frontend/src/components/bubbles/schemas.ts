import type { Message, PublicConfig, Turn } from '../../api/schemas'

export interface ChatBubbleProps {
  message: Message
  turn?: Turn
  config?: PublicConfig | null
}
