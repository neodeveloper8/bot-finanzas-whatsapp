// Corre ANTES de pintar la página para evitar el "flash" blanco en modo oscuro.
// En producción esta misma lógica va en línea dentro de app.html.
try {
  const guardado = localStorage.getItem('tema')
  const oscuro = guardado ? guardado === 'oscuro' : matchMedia('(prefers-color-scheme: dark)').matches
  document.documentElement.classList.toggle('dark', oscuro)
} catch {
  /* sin localStorage (modo privado estricto): se queda en claro */
}
