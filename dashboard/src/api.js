// Calls to the dashboard's own server. With CIDRA_DASHBOARD_TOKEN set the server
// wants it in X-CIDRA-Token; `cidra dashboard` opens the page as /#token=<token>.
// The token moves from the address bar to this tab's sessionStorage.
const KEY = 'cidra-token';

export const AUTH_HELP = 'This dashboard needs its access token. Open the link that `cidra dashboard` printed (it ends in #token=...).';

function token() {
  try {
    const m = window.location.hash.match(/token=([^&]+)/);
    if (m) {
      sessionStorage.setItem(KEY, decodeURIComponent(m[1]));
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    return sessionStorage.getItem(KEY) || '';
  } catch {
    return '';
  }
}

export function apiFetch(url, options = {}) {
  const t = token();
  return fetch(url, t ? { ...options, headers: { ...options.headers, 'X-CIDRA-Token': t } } : options);
}
