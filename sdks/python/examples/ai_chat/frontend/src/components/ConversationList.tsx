import type { Conversation } from '../api/schemas'

interface ConversationListProps {
  conversations: Conversation[]
  selectedConversationId: string | null
  loading: boolean
  disabled: boolean
  onSelect: (conversationId: string) => void
}

export function ConversationList({
  conversations,
  selectedConversationId,
  loading,
  disabled,
  onSelect,
}: ConversationListProps) {
  return (
    <aside className="conversation-panel" aria-label="Conversations">
      <div className="conversation-heading">
        <span className="eyebrow">Junjo example</span>
        <h1>Agent chat</h1>
      </div>
      <nav aria-label="Conversation list">
        {loading && <p className="quiet-copy">Loading conversations…</p>}
        {!loading && conversations.length === 0 && (
          <p className="quiet-copy">No conversations are available.</p>
        )}
        <ul className="conversation-list">
          {conversations.map((conversation) => (
            <li key={conversation.id}>
              <button
                type="button"
                className="conversation-button"
                aria-current={conversation.id === selectedConversationId ? 'page' : undefined}
                disabled={disabled}
                onClick={() => onSelect(conversation.id)}
              >
                <span>{conversation.title}</span>
                <small>{conversation.id}</small>
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}
