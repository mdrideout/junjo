export default function ChatForm() {
  return (
    <div className="p-4 grid grid-cols-[auto_100px] gap-x-2 items-end">
      <div>
        <textarea
          className={'w-full rounded-md bg-zinc-300 text-zinc-800 px-3 py-2 leading-tight border-0 ring-0 outline-0'}
          rows={3}
          placeholder="Send a chat..."
        ></textarea>
      </div>
      <div className="h-full pb-1.5">
        <button className="w-full h-full cursor-pointer border border-blue-300 rounded-md bg-gradient-to-b from-blue-600 to-blue-700 hover:to-blue-800 text-white leading-none px-3 py-1">
          Send
        </button>
      </div>
    </div>
  )
}
