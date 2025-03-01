export default function ChatForm() {
  return (
    <div className="p-4 grid grid-cols-[auto_100px] gap-x-2 items-end">
      <div>
        <textarea
          className={'w-full rounded-md bg-zinc-200 text-zinc-800 px-3 py-2 leading-tight'}
          rows={3}
          placeholder="Send a chat..."
        ></textarea>
      </div>
      <div className="h-full pb-1.5">
        <button className="w-full h-full border border-blue-300 rounded-md bg-blue-600 text-white leading-none px-3 py-1">
          Send
        </button>
      </div>
    </div>
  )
}
