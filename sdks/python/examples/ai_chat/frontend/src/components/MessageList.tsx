import type { Message, TurnEvidence } from '../api/schemas'
import { resolveApiAssetUrl } from '../api/client'

interface MessageListProps {
  messages: Message[]
  evidenceByTurnId: Record<string, TurnEvidence>
  loading: boolean
  hasConversation: boolean
}

function messageTime(timestamp: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp))
}

export function MessageList({
  messages,
  evidenceByTurnId,
  loading,
  hasConversation,
}: MessageListProps) {
  if (!hasConversation) {
    return <div className="message-empty">Select a conversation to begin.</div>
  }
  if (loading) {
    return <div className="message-empty">Loading messages…</div>
  }
  if (messages.length === 0) {
    return <div className="message-empty">This conversation has no messages yet.</div>
  }

  return (
    <ol className="message-list" aria-label="Messages">
      {messages.map((message) => {
        const evidence = message.role === 'assistant'
          ? evidenceByTurnId[message.turn_id]
          : undefined
        return (
          <li key={message.id} className={`message-row message-row-${message.role}`}>
            <article className="message-card">
              <div className="message-meta">
                <span>{message.role === 'assistant' ? 'Agent' : 'You'}</span>
                <time dateTime={message.created_at}>{messageTime(message.created_at)}</time>
              </div>
              <p>{message.content}</p>
              {message.image_url !== null && message.image_alt !== null && (
                <img src={resolveApiAssetUrl(message.image_url)} alt={message.image_alt} />
              )}
              {evidence !== undefined && (
                <dl className="evidence-links" aria-label="Execution evidence">
                  <div>
                    <dt>Workflow run</dt>
                    <dd>{evidence.workflowRunId}</dd>
                  </div>
                  <div>
                    <dt>Agent run</dt>
                    <dd>{evidence.agentRunId}</dd>
                  </div>
                </dl>
              )}
            </article>
          </li>
        )
      })}
    </ol>
  )
}
