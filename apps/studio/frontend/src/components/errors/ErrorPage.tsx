export type ErrorPageProps = {
  title: string
  message: string
}

export default function ErrorPage(props: ErrorPageProps) {
  return (
    <div className={'p-5'}>
      <h1>{props.title}</h1>
      <div className="h-2"></div>
      <p>{props.message}</p>
    </div>
  )
}
