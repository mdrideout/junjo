export default function DashboardPage() {
  // Render the users list
  return (
    <div className={'px-3 py-4 flex flex-col h-dvh overflow-hidden'}>
      <div className={'flex gap-x-3 px-2 items-center'}>
        <div className={'flex gap-x-3 font-bold'}>Dashboard</div>
      </div>
      <hr className={'my-4'} />
      <div className={'px-2'}>
        <p>
          Welcome to Junjo Server. The Dashboard is on our roadmap. For now, head to your{' '}
          <a href="/logs" className={'underline'}>
            logs
          </a>
          .
        </p>
      </div>
    </div>
  )
}
