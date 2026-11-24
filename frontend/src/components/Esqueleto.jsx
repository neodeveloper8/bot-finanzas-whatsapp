/** Bloques grises que "laten" mientras llegan los datos: la página no salta al cargar. */
export const Bloque = ({ className = '' }) => (
  <div className={`animate-pulse rounded-md bg-fondo-hover ${className}`} />
)

export function EsqueletoResumen() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Cargando resumen">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        {[0, 1, 2].map((i) => (
          <Bloque key={i} className="h-[104px] rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Bloque className="h-[250px] rounded-xl" />
        <Bloque className="h-[250px] rounded-xl" />
      </div>
    </div>
  )
}
