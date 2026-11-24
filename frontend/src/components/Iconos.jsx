// Íconos de trazo, en línea: heredan el color del texto (currentColor) y
// no dependen de ninguna librería ni de descargas extra.
function Icono({ children, tam = 18, ancho = 1.8, ...props }) {
  return (
    <svg
      width={tam}
      height={tam}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={ancho}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

export const IconoResumen = (p) => (
  <Icono {...p}>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Icono>
)
export const IconoLista = (p) => (
  <Icono {...p}>
    <line x1="8" y1="6" x2="21" y2="6" />
    <line x1="8" y1="12" x2="21" y2="12" />
    <line x1="8" y1="18" x2="21" y2="18" />
    <circle cx="4" cy="6" r="1" />
    <circle cx="4" cy="12" r="1" />
    <circle cx="4" cy="18" r="1" />
  </Icono>
)
export const IconoSalir = (p) => (
  <Icono {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </Icono>
)
export const IconoBuscar = (p) => (
  <Icono {...p}>
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.5" y2="16.5" />
  </Icono>
)
export const IconoLapiz = (p) => (
  <Icono {...p}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </Icono>
)
export const IconoMas = (p) => (
  <Icono {...p}>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </Icono>
)
export const IconoBasura = (p) => (
  <Icono {...p}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </Icono>
)
export const IconoFlechaAbajo = (p) => (
  <Icono ancho={2} {...p}>
    <polyline points="6 9 12 15 18 9" />
  </Icono>
)
export const IconoCelular = (p) => (
  <Icono {...p}>
    <rect x="6" y="2" width="12" height="20" rx="2.5" />
    <line x1="11" y1="18" x2="13" y2="18" />
  </Icono>
)
export const IconoMensaje = (p) => (
  <Icono {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
  </Icono>
)
export const IconoSol = (p) => (
  <Icono {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icono>
)
export const IconoLuna = (p) => (
  <Icono {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Icono>
)
export const IconoPantalla = (p) => (
  <Icono {...p}>
    <rect x="2" y="4" width="20" height="13" rx="2" />
    <path d="M8 21h8M12 17v4" />
  </Icono>
)
export const IconoAnterior = (p) => (
  <Icono ancho={2} {...p}>
    <polyline points="15 18 9 12 15 6" />
  </Icono>
)
export const IconoSiguiente = (p) => (
  <Icono ancho={2} {...p}>
    <polyline points="9 18 15 12 9 6" />
  </Icono>
)
