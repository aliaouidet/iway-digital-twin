// API/WS host is taken from the browser's address bar so a single dev build works
// whether the app is opened at localhost (local dev) or the server's LAN IP
// (on-prem deploy, e.g. http://192.168.111.119:4200). Ports are fixed by docker-compose.
// Falls back to localhost for non-browser contexts.
const host = (typeof window !== 'undefined' && window.location && window.location.hostname) || 'localhost';

export const environment = {
  production: false,
  apiUrl: `http://${host}:8000`,
  wsUrl: `ws://${host}:8000/ws/events`,
  jaegerUrl: `http://${host}:16686`
};
