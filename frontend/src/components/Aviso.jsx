/** Aviso flotante abajo al centro ("toast"). role=status: los lectores de pantalla lo leen solos. */
export default function Aviso({ aviso }) {
  if (!aviso) return null
  return (
    <div
      role="status"
      className="fixed bottom-[88px] left-1/2 z-30 flex max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-4 rounded-lg bg-[#2F2E2B] py-2.5 pr-3 pl-4 text-[13px] text-white shadow-xl md:bottom-6 dark:bg-[#E6E5E3] dark:text-[#191919]"
    >
      <span>{aviso.texto}</span>
      {aviso.deshacer && (
        <button
          type="button"
          onClick={aviso.deshacer}
          className="min-h-8 cursor-pointer px-2 font-semibold text-[#9CC3F5] dark:text-[#1F5A8A]"
        >
          Deshacer
        </button>
      )}
    </div>
  )
}
