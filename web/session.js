/**
 * Shared browser session helpers: auth gate, bearer headers, 401 redirect.
 */

function redirectToLoginIfUnauthenticated() {
    const token = localStorage.getItem('auth_token');
    const playerId = localStorage.getItem('player_id');
    if (!token || !playerId) {
        window.location.href = 'login.html';
        return true;
    }
    return false;
}

function clearAuthAndGoLogin() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('player_id');
    localStorage.removeItem('username');
    window.location.href = 'login.html';
}

function authHeaders(existingHeaders = {}) {
    const token = localStorage.getItem('auth_token');
    const base = typeof existingHeaders === 'object' && existingHeaders !== null ? { ...existingHeaders } : {};
    if (token) {
        base.Authorization = `Bearer ${token}`;
    }
    return base;
}

/**
 * fetch() with Bearer token merged into headers.
 * On 401, clears session and redirects to login; returns null in that case.
 */
async function fetchWithAuth(url, options = {}) {
    const headers = authHeaders(options.headers || {});
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        clearAuthAndGoLogin();
        return null;
    }
    return response;
}
