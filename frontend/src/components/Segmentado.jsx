/**
 * Botones tipo "píldora" para elegir una opción (período, tipo de movimiento).
 * `lleno`: en el celular (< 640 px) ocupa todo el ancho y reparte los botones en
 * partes iguales; desde 640 px se ve igual que sin la opción.
 */
export default function Segmentado({ opciones, valor, alCambiar, etiqueta, chico = false, lleno = false }) {
  return (
    <div
      role="group"
      aria-label={etiqueta}
      className={`flex gap-0.5 rounded-lg bg-fondo-hover p-[3px] ${lleno ? 'w-full sm:w-auto' : ''}`}
    >
      {opciones.map((o) => {
        const activo = o.valor === valor
        return (
          <button
            key={o.valor}
            type="button"
            aria-pressed={activo}
            aria-label={o.titulo}
            title={o.titulo}
            onClick={() => alCambiar(o.valor)}
            className={[
              'shrink-0 cursor-pointer rounded-md font-medium whitespace-nowrap transition-colors',
              chico
                ? 'min-h-[30px] px-2.5 text-[13px]'
                : lleno
                  ? // Celular: mismo ancho para todos y texto más compacto para que entren.
                    // Va en vez de "px-3 text-[13px]" (no además): dos clases de padding
                    // juntas no se pisan por orden, depende del orden del CSS generado.
                    'min-h-[34px] min-w-0 flex-1 px-0.5 text-[12px] sm:flex-none sm:px-3 sm:text-[13px]'
                  : 'min-h-[34px] px-3 text-[13px]',
              activo
                ? 'bg-fondo text-texto shadow-[0_1px_2px_rgba(15,15,15,0.12)] dark:bg-fondo-suave'
                : 'text-texto-suave hover:text-texto',
            ].join(' ')}
          >
            {o.etiqueta}
          </button>
        )
      })}
    </div>
  )
}
