import { leerCookie } from '../lib/api'
import { useTema } from '../lib/tema'
import { IconoLista, IconoLuna, IconoMas, IconoPantalla, IconoResumen, IconoSalir, IconoSol } from './Iconos'
import Segmentado from './Segmentado'

const TEMAS = [
  { valor: 'claro', etiqueta: <IconoSol tam={16} />, titulo: 'Tema claro' },
  { valor: 'sistema', etiqueta: <IconoPantalla tam={16} />, titulo: 'Tema del sistema' },
  { valor: 'oscuro', etiqueta: <IconoLuna tam={16} />, titulo: 'Tema oscuro' },
]

function SelectorTema() {
  const { preferencia, elegir } = useTema()
  return <Segmentado opciones={TEMAS} valor={preferencia} alCambiar={elegir} etiqueta="Tema" chico />
}

/** Formulario normal (no fetch): el servidor responde con un redirect y el navegador lo sigue solo. */
function BotonSalir({ className = '' }) {
  return (
    <form method="post" action="/panel/salir/">
      <input type="hidden" name="csrfmiddlewaretoken" value={leerCookie('csrftoken')} />
      <button
        type="submit"
        className={`flex min-h-9 w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-left text-sm text-texto-medio hover:bg-fondo-hover ${className}`}
      >
        <IconoSalir />
        Cerrar sesión
      </button>
    </form>
  )
}

function Avatar({ nombre, tam = 'size-7' }) {
  return (
    <div
      aria-hidden="true"
      className={`${tam} flex shrink-0 items-center justify-center rounded-full bg-[#E3EDF7] text-xs font-semibold text-[#1F5A8A] dark:bg-[#1E3346] dark:text-[#93C0EA]`}
    >
      {(nombre || '?').charAt(0).toUpperCase()}
    </div>
  )
}

const ENLACES = [
  { href: '#resumen', etiqueta: 'Resumen', Icono: IconoResumen },
  { href: '#movimientos', etiqueta: 'Movimientos', Icono: IconoLista },
]

/** `alAgregar` null = solo lectura (demo): no se muestra el botón. */
export function BarraLateral({ nombre, alAgregar, esDemo = false }) {
  return (
    <nav
      aria-label="Navegación principal"
      className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-1 border-r border-borde bg-fondo-suave px-3 py-5 md:flex"
    >
      <div className="flex items-center gap-2.5 px-2.5 pb-5">
        <div className="flex size-7 items-center justify-center rounded-md bg-texto text-xs font-bold text-fondo">
          S/
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">Mis finanzas</span>
          <span className="text-xs text-texto-suave">Panel del bot</span>
        </div>
      </div>

      {ENLACES.map(({ href, etiqueta, Icono }) => (
        <a
          key={href}
          href={href}
          className="flex min-h-9 items-center gap-2.5 rounded-md px-2.5 text-sm font-medium text-texto-medio hover:bg-fondo-hover hover:text-texto"
        >
          <Icono />
          {etiqueta}
        </a>
      ))}
      {alAgregar && (
        <button
          type="button"
          onClick={alAgregar}
          className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-left text-sm font-medium text-acento hover:bg-fondo-hover"
        >
          <IconoMas />
          Agregar movimiento
        </button>
      )}

      <div className="mt-auto flex flex-col gap-3 pt-6">
        <div className="px-2.5">
          <SelectorTema />
        </div>
        <div className="flex items-center gap-2.5 px-2.5">
          <Avatar nombre={nombre} />
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-[13px] font-medium">{nombre || 'Tu cuenta'}</span>
            <span className="text-xs text-texto-suave">
              {esDemo ? 'Demo · datos ficticios' : 'Sesión activa · 30 días'}
            </span>
          </div>
        </div>
        <BotonSalir />
      </div>
    </nav>
  )
}

/** En el celular: arriba el avatar con un menú (tema y salir), abajo la navegación. */
export function CabeceraMovil({ nombre }) {
  return (
    <header className="flex items-center justify-between px-4 pt-4 md:hidden">
      <span className="text-sm font-semibold">Mis finanzas</span>
      <details className="relative">
        <summary className="flex size-11 cursor-pointer list-none items-center justify-center rounded-full [&::-webkit-details-marker]:hidden">
          <Avatar nombre={nombre} tam="size-9" />
          <span className="sr-only">Menú de la cuenta</span>
        </summary>
        <div className="absolute right-0 z-20 mt-1 flex w-56 flex-col gap-3 rounded-xl border border-borde bg-fondo p-3 shadow-lg">
          <span className="truncate px-1 text-[13px] font-medium">{nombre || 'Tu cuenta'}</span>
          <SelectorTema />
          <BotonSalir className="px-1" />
        </div>
      </details>
    </header>
  )
}

const ENLACE_INFERIOR = 'flex min-h-11 flex-col items-center justify-center gap-0.5 text-[11px] font-medium text-texto-suave'

export function BarraInferior({ alAgregar }) {
  const [resumen, movimientos] = ENLACES
  const enlace = ({ href, etiqueta, Icono }) => (
    <a key={href} href={href} className={ENLACE_INFERIOR}>
      <Icono tam={22} />
      {etiqueta}
    </a>
  )
  return (
    <nav
      aria-label="Navegación principal"
      className={`fixed inset-x-0 bottom-0 z-10 grid ${alAgregar ? 'grid-cols-3' : 'grid-cols-2'} border-t border-borde bg-fondo/95 px-2 pt-1.5 pb-[max(env(safe-area-inset-bottom),12px)] backdrop-blur md:hidden`}
    >
      {enlace(resumen)}
      {/* Al centro y destacado: es lo que más vas a usar desde el celular */}
      {alAgregar && (
        <button type="button" onClick={alAgregar} className={`${ENLACE_INFERIOR} cursor-pointer text-acento`}>
          <span className="flex size-[30px] items-center justify-center rounded-full bg-acento text-white dark:text-[#191919]">
            <IconoMas tam={20} ancho={2.2} />
          </span>
          Agregar
        </button>
      )}
      {enlace(movimientos)}
    </nav>
  )
}
