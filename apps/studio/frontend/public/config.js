// Default runtime config for local development (e.g. Vite).
// The production container overwrites `/config.js` at startup (see `frontend/prod-startup.sh`).
window.runtimeConfig = window.runtimeConfig || { API_HOST: 'http://localhost:1323' }

