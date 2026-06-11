// Same dynamic-host mechanism as dev (environment.ts): the API/WS host comes
// from the browser's address bar, so one production build works at any deploy
// address (localhost, LAN IP, future domain) without rebuilding.
const host = (typeof window !== 'undefined' && window.location && window.location.hostname) || 'localhost';

export const environment = {
  production: true,
  apiUrl: `http://${host}:8000`,
  wsUrl: `ws://${host}:8000/ws/events`,
  jaegerUrl: ''   // ops UIs are localhost-bound in prod — hide trace links
};
