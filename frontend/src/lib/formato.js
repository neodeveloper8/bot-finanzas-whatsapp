// Los montos llegan como TEXTO ("1234.50"). Aquí solo les damos formato:
// nunca los sumamos con floats. Para porcentajes usamos céntimos enteros.

export function soles(texto, { signo = false } = {}) {
  const negativo = texto.startsWith('-')
  const [entero, decimales = '00'] = texto.replace('-', '').split('.')
  const conComas = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const prefijo = negativo ? '−' : signo ? '+' : ''
  return `${prefijo}S/ ${conComas}.${decimales}`
}

export const centimos = (texto) => Math.round(Number(texto) * 100)

/** % de cambio entero, o null si antes era 0 (no se puede dividir entre 0). */
export function cambioPorcentual(actual, anterior) {
  const a = centimos(actual)
  const b = centimos(anterior)
  if (b === 0) return null
  return Math.round(((a - b) / b) * 100)
}

const ZONA = 'America/Lima'
const fmtDia = new Intl.DateTimeFormat('es-PE', { day: 'numeric', month: 'short', timeZone: ZONA })
const fmtHora = new Intl.DateTimeFormat('es-PE', { hour: 'numeric', minute: '2-digit', timeZone: ZONA })
const fmtLargo = new Intl.DateTimeFormat('es-PE', { day: 'numeric', month: 'long', timeZone: ZONA })

const fmtISO = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: ZONA })

/** "2026-11-20": la fecha en LIMA (no la del navegador), lista para un <input type="date">. */
export const fechaISOLima = (momento = new Date()) => fmtISO.format(momento)
/** Lima no tiene horario de verano: restar 24 h siempre da "ayer". */
export const ayerISOLima = () => fechaISOLima(new Date(Date.now() - 86_400_000))

/** "2026-11-19" + 1 -> "2026-11-20". Pasa por el mediodía de Lima: nunca se corre de día. */
export const sumarDias = (iso, n) => fechaISOLima(new Date(Date.parse(`${iso}T12:00:00-05:00`) + n * 86_400_000))

/** Días entre dos fechas ISO (b - a). */
export const diasEntre = (a, b) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 86_400_000)

const sinPunto = (s) => s.replace('.', '')

export const fechaCorta = (iso) => sinPunto(fmtDia.format(new Date(iso))) // "19 nov"
export const hora = (iso) => fmtHora.format(new Date(iso)) // "9:42 a. m."

/** "2026-11-01", "2026-11-20" -> "Del 1 al 20 de noviembre" */
export function rangoLegible(desde, hasta) {
  // T12:00 para que la fecha "pura" no se corra de día al pasar por la zona horaria
  const d = new Date(`${desde}T12:00:00-05:00`)
  const h = new Date(`${hasta}T12:00:00-05:00`)
  if (desde === hasta) return fmtLargo.format(d)
  const mismoMes = desde.slice(0, 7) === hasta.slice(0, 7)
  return mismoMes
    ? `Del ${d.getUTCDate()} al ${fmtLargo.format(h)}`
    : `Del ${fmtLargo.format(d)} al ${fmtLargo.format(h)}`
}
