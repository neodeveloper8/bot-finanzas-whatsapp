import { useRef } from 'react'

import { fechaCorta, fechaISOLima } from '../lib/formato'

/**
 * Píldora "📅 Elegir día" que abre el calendario del navegador.
 *
 * El <input type="date"> está ENCIMA de la píldora, transparente: en el celular,
 * tocarlo abre el calendario nativo. En la computadora, ese toque solo lo enfocaría,
 * así que además llamamos a showPicker(), que abre el calendario directamente.
 */
export default function SelectorDia({ fecha, activo, alElegir }) {
  const entrada = useRef(null)
  const hoy = fechaISOLima()

  function abrir() {
    try {
      entrada.current.showPicker()
    } catch {
      /* navegador viejo: el toque sobre el input ya abre su calendario */
    }
  }

  return (
    <div
      className={[
        'relative flex min-h-[40px] shrink-0 items-center rounded-lg px-3 text-[13px] font-medium whitespace-nowrap',
        activo
          ? 'bg-fondo text-texto shadow-[0_1px_2px_rgba(15,15,15,0.12)] ring-1 ring-borde-fuerte dark:bg-fondo-suave'
          : 'bg-fondo-hover text-texto-suave hover:text-texto',
      ].join(' ')}
    >
      <span aria-hidden="true">📅 {activo && fecha ? fechaCorta(`${fecha}T12:00:00-05:00`) : 'Elegir día'}</span>
      <input
        ref={entrada}
        type="date"
        max={hoy}
        value={fecha ?? ''}
        onClick={abrir}
        onChange={(e) => e.target.value && alElegir(e.target.value)}
        aria-label="Ver un día"
        className="absolute inset-0 cursor-pointer opacity-0"
      />
    </div>
  )
}
