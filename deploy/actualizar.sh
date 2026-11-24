#!/usr/bin/env bash
# Despliega la última versión de main. Se corre como botfin:  ~/bot-finanzas/deploy/actualizar.sh
set -euo pipefail  # si un paso falla, se detiene (no sigue migrando con código a medias)

cd /home/botfin/bot-finanzas

# 1) Traer el código nuevo. Si ESTE script cambió en el pull, bash seguiría
#    ejecutando la versión vieja que ya leyó. Por eso, tras el pull, se vuelve
#    a lanzar a sí mismo (exec) con la versión nueva. La variable evita un bucle.
if [ "${YA_ACTUALIZADO:-}" != "1" ]; then
  git pull --ff-only                     # --ff-only: falla si hay cambios locales en el servidor
  YA_ACTUALIZADO=1 exec bash "$0" "$@"
fi

uv pip install -r requirements.txt       # uv detecta el .venv de esta carpeta
.venv/bin/python manage.py migrate --noinput

# Panel (React): se compila AQUÍ con el Node de botfin, no el del sistema (ese es de los otros sistemas del servidor)
export PATH="$HOME/.local/node/bin:$PATH"
(cd frontend && npm ci --no-audit --no-fund && npm run build)

.venv/bin/python manage.py collectstatic --noinput   # después del build: recoge panel.js/css
pm2 reload deploy/ecosystem.config.js
echo "✅ Bot actualizado"
