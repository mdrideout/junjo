import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import DeveloperCredentialsPage from './DeveloperCredentialsPage'

describe('DeveloperCredentialsPage', () => {
  it('keeps evaluation control and telemetry ingestion credentials explicit', () => {
    render(
      <MemoryRouter>
        <DeveloperCredentialsPage />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('link', { name: 'Manage evaluation tokens' }),
    ).toHaveAttribute('href', '/settings/credentials/evaluation')
    expect(
      screen.getByRole('link', { name: 'Manage ingestion API keys' }),
    ).toHaveAttribute('href', '/settings/credentials/ingestion')
    expect(screen.getByText(/cannot ingest telemetry/i)).toBeInTheDocument()
    expect(screen.getByText(/do not grant dataset/i)).toBeInTheDocument()
  })
})
