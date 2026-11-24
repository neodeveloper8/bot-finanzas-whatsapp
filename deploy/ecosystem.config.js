// PM2: los dos procesos del bot. Se usa desde el usuario botfin:
//   pm2 start deploy/ecosystem.config.js   (la primera vez)
//   pm2 reload deploy/ecosystem.config.js  (en cada actualización)
const APP = "/home/botfin/bot-finanzas";

module.exports = {
  apps: [
    {
      name: "botfin-web",
      cwd: APP,
      script: `${APP}/.venv/bin/gunicorn`,
      // 127.0.0.1: SOLO accesible desde el propio servidor; afuera se entra por nginx
      args: "config.wsgi:application --bind 127.0.0.1:8010 --workers 2 --timeout 30",
      interpreter: "none", // gunicorn ya es un ejecutable; PM2 no debe envolverlo con node
      max_memory_restart: "300M", // si se descontrola, se reinicia ANTES de afectar a los otros servicios del servidor
      autorestart: true,
    },
    {
      name: "botfin-worker",
      cwd: APP,
      script: `${APP}/.venv/bin/python`,
      args: "manage.py qcluster",
      interpreter: "none",
      max_memory_restart: "300M",
      autorestart: true,
      kill_timeout: 10000, // le da 10 s para terminar la tarea en curso antes de matarlo
    },
  ],
};
