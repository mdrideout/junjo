import { AppLink } from '../../components/navigation/app-link'

export default function DeveloperCredentialsPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-5 p-4 sm:p-6">
      <header>
        <h1 className="m-0 text-3xl">Developer credentials</h1>
        <p className="mt-2 max-w-3xl text-sm text-[var(--studio-text-muted)]">
          Studio keeps telemetry ingestion credentials separate from evaluation
          control and evidence credentials. Choose the credential for the system
          interaction you are configuring.
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-5">
          <h2 className="m-0 text-xl">Evaluation tokens</h2>
          <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
            Scoped credentials for the Junjo SDK and CLI to manage datasets,
            execute evaluation runs, and query evidence. They cannot ingest telemetry.
          </p>
          <div className="mt-4">
            <AppLink to="/settings/credentials/evaluation">
              Manage evaluation tokens
            </AppLink>
          </div>
        </article>
        <article className="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-surface-raised)] p-5">
          <h2 className="m-0 text-xl">Ingestion API keys</h2>
          <p className="mt-2 text-sm text-[var(--studio-text-muted)]">
            Application credentials for OTLP telemetry delivery. They do not grant
            dataset, evaluation-run, or evidence query access.
          </p>
          <div className="mt-4">
            <AppLink to="/settings/credentials/ingestion">
              Manage ingestion API keys
            </AppLink>
          </div>
        </article>
      </div>
    </div>
  )
}
