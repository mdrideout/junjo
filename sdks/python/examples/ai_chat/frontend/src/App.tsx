import { ConversationList } from './components/ConversationList'
import { MessageList } from './components/MessageList'
import { TurnForm } from './components/TurnForm'
import { useChat } from './hooks/useChat'

export default function App() {
  const chat = useChat()
  const selectedConversation = chat.conversations.find(
    (conversation) => conversation.id === chat.selectedConversationId,
  )

  return (
    <div className="app-shell">
      <ConversationList
        conversations={chat.conversations}
        selectedConversationId={chat.selectedConversationId}
        loading={chat.loadingConversations}
        disabled={chat.sending}
        onSelect={chat.selectConversation}
      />
      <main className="chat-panel">
        <header className="chat-heading">
          <div>
            <span className="eyebrow">Deterministic execution evidence</span>
            <h2>{selectedConversation?.title ?? 'Conversation'}</h2>
          </div>
          {chat.selectedConversationId !== null && (
            <code>{chat.selectedConversationId}</code>
          )}
        </header>
        {chat.error !== null && (
          <div className="error-banner" role="alert">
            <p>{chat.error.message}</p>
            {chat.error.agentRunId !== null && chat.error.terminationReason !== null && (
              <dl aria-label="Failed Agent execution evidence">
                <div>
                  <dt>Agent run</dt>
                  <dd>{chat.error.agentRunId}</dd>
                </div>
                <div>
                  <dt>Reason</dt>
                  <dd>{chat.error.terminationReason}</dd>
                </div>
              </dl>
            )}
          </div>
        )}
        <section className="message-panel" aria-label="Active conversation">
          <MessageList
            messages={chat.messages}
            evidenceByTurnId={chat.evidenceByTurnId}
            loading={chat.loadingMessages}
            hasConversation={chat.selectedConversationId !== null}
          />
        </section>
        <TurnForm
          disabled={chat.selectedConversationId === null || chat.loadingMessages}
          sending={chat.sending}
          onSubmit={chat.sendTurn}
        />
      </main>
    </div>
  )
}
