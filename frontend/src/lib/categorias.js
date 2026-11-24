// Colores tipo "etiqueta de Notion". Van por nombre de categoría (las del
// sistema) y, para las que crees tú, se reparten en orden. Cada una trae su
// versión clara y oscura: un pastel claro sobre fondo negro se ve mal.

const PALETA = {
  naranja: { dot: '#E08A3C', claro: ['#FBECDD', '#8A4A16'], oscuro: ['#4A2E19', '#F2B680'] },
  azul: { dot: '#4A8BC9', claro: ['#E3EDF7', '#1F5A8A'], oscuro: ['#1E3346', '#93C0EA'] },
  morado: { dot: '#9068C4', claro: ['#EEE6F6', '#5E3C8C'], oscuro: ['#352848', '#C5A9EA'] },
  verde: { dot: '#5BA36B', claro: ['#E4F0E6', '#2E6B3D'], oscuro: ['#1F3826', '#9AD3A8'] },
  rosa: { dot: '#D06A97', claro: ['#F7E4EC', '#8C2F5A'], oscuro: ['#47222F', '#EDA3C3'] },
  amarillo: { dot: '#D9B23F', claro: ['#FAF0D2', '#6E5200'], oscuro: ['#43391A', '#EBCF7A'] },
  cafe: { dot: '#A47A5C', claro: ['#F2E9E2', '#6B4A33'], oscuro: ['#3B2D24', '#D5B8A2'] },
  turquesa: { dot: '#3FA3A0', claro: ['#DFF1F0', '#1F6664'], oscuro: ['#173836', '#8FD4D1'] },
  gris: { dot: '#9B9A97', claro: ['#EFEFED', '#5F5E5A'], oscuro: ['#2F2F2F', '#BDBCB8'] },
}

const POR_NOMBRE = {
  Comida: 'naranja',
  Transporte: 'morado',
  Compras: 'azul',
  Hogar: 'cafe',
  Salud: 'rosa',
  Entretenimiento: 'amarillo',
  Familia: 'turquesa',
  Servicios: 'verde',
  Otros: 'gris',
  // De ingreso
  Sueldo: 'verde',
  InDrive: 'amarillo',
  'Otros ingresos': 'gris',
}
const ROTACION = ['azul', 'verde', 'morado', 'naranja', 'rosa', 'turquesa', 'amarillo', 'cafe']

export function colorCategoria(nombre, oscuro) {
  let clave = nombre ? POR_NOMBRE[nombre] : 'gris'
  if (!clave) {
    // Categoría propia: color estable según su nombre (siempre el mismo)
    const suma = [...nombre].reduce((t, c) => t + c.charCodeAt(0), 0)
    clave = ROTACION[suma % ROTACION.length]
  }
  const c = PALETA[clave]
  const [fondo, texto] = oscuro ? c.oscuro : c.claro
  return { punto: c.dot, fondo, texto }
}
