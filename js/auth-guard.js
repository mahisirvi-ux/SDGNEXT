/**
 * js/auth-guard.js
 * ─────────────────
 * Drop-in auth guard for all protected pages.
 *
 * Usage: add ONE script tag before any other scripts on every protected page:
 *   <script src="/js/auth-guard.js"></script>
 *
 * What it does:
 *   1. Reads the JWT from localStorage ("sdgnext_token").
 *   2. If missing → redirect to /login immediately.
 *   3. If present  → attaches it to every fetch() call via a global patch
 *      so all existing API calls are automatically authenticated.
 *   4. Exposes window.SDGAuth.user (decoded payload) and window.SDGAuth.logout().
 */

(function () {
    "use strict";

    const TOKEN_KEY = "sdgnext_token";
    const USER_KEY  = "sdgnext_user";
    const LOGIN_URL = "/login";

    // ── Read stored token ────────────────────────────────────────────────────
    const token = localStorage.getItem(TOKEN_KEY);

    if (!token) {
        window.location.replace(LOGIN_URL);
        // Stop all JS execution on this page — nothing should render without auth
        throw new Error("SDGAuth: no token, redirecting to login");
    }

    // ── Decode JWT payload (no signature verification — that's the server's job) ──
    function decodeJWT(t) {
        try {
            const base64 = t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
            return JSON.parse(atob(base64));
        } catch {
            return null;
        }
    }

    const payload = decodeJWT(token);

    // ── Expiry check (client-side early detection) ───────────────────────────
    if (!payload || (payload.exp && Date.now() / 1000 > payload.exp)) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        window.location.replace(LOGIN_URL + "?reason=expired");
        throw new Error("SDGAuth: token expired");
    }

    // ── Patch global fetch to inject Authorization header ────────────────────
    const _nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init = {}) {
        const url = typeof input === "string" ? input : input?.url ?? "";
        // Only inject for same-origin API calls (not CDN, fonts, etc.)
        const isApiCall = url.startsWith("/api/") || url.startsWith("/admin/");
        if (isApiCall) {
            init.headers = Object.assign(
                { "Authorization": `Bearer ${token}` },
                init.headers || {}
            );
        }
        return _nativeFetch(input, init);
    };

    // ── SDGAuth public API ───────────────────────────────────────────────────
    const storedUser = (() => {
        try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); }
        catch { return null; }
    })();

    window.SDGAuth = {
        token,
        user: storedUser || payload,

        /** Log out: clear storage and go to login page. */
        logout() {
            localStorage.removeItem(TOKEN_KEY);
            localStorage.removeItem(USER_KEY);
            window.location.replace(LOGIN_URL + "?reason=logout");
        },

        /** Returns true if the current user has a given role or above.
         *  Role hierarchy: admin > manager > viewer */
        hasRole(required) {
            const rank = { admin: 3, manager: 2, viewer: 1 };
            const mine = rank[this.user?.role] ?? 0;
            return mine >= (rank[required] ?? 99);
        },
    };

    // ── Inject user badge into header (if present) ───────────────────────────
    document.addEventListener("DOMContentLoaded", () => {
        _renderUserBadge();
    });

    function _renderUserBadge() {
        const u = window.SDGAuth.user;
        const initials = (u?.full_name || u?.sub || "?")
            .split(" ").slice(0, 2).map(w => w[0]).join("").toUpperCase();

        const badge = document.createElement("div");
        badge.id = "sdg-user-badge";
        badge.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;background:rgba(255,255,255,0.10);border:1px solid rgba(255,255,255,0.20);border-radius:9999px;padding:5px 14px 5px 6px;cursor:pointer;transition:background 0.2s;" 
                 onmouseover="this.style.background='rgba(255,255,255,0.18)'" 
                 onmouseout="this.style.background='rgba(255,255,255,0.10)'" 
                 onclick="SDGAuth.logout()" 
                 title="Logout — ${u?.full_name || u?.sub || ''}">
                <div style="width:28px;height:28px;border-radius:50%;background:#ec4899;color:white;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 0 0 2px rgba(236,72,153,0.35);">${initials}</div>
                <span style="font-size:12px;font-weight:600;color:rgba(255,255,255,0.92);white-space:nowrap;">${u?.full_name || u?.sub || "User"}</span>
                <svg style="width:14px;height:14px;color:rgba(255,255,255,0.55);flex-shrink:0;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
                </svg>
            </div>
        `;

        // ── Strategy 1: explicit anchor div on the page ──────────────────────
        const explicitAnchor = document.getElementById("user-badge-anchor");
        if (explicitAnchor) {
            explicitAnchor.innerHTML = "";
            explicitAnchor.appendChild(badge);
            return;
        }

        // ── Strategy 2: index.html — header is itself a flex justify-between row
        //    append inside the right-side button group (.flex.items-center.space-x-4)
        const btnGroup = document.querySelector("header .flex.items-center.space-x-4");
        if (btnGroup) {
            btnGroup.appendChild(badge);
            return;
        }

        // ── Strategy 3: landing.html / details.html
        //    header > div[justify-between]  — append to that inner div so flex
        //    pushes the badge all the way to the RIGHT
        const innerRow = document.querySelector(
            "header > div.flex, header > div[class*='flex']"
        );
        if (innerRow) {
            // Ensure the row is justify-between so new child goes to far right
            innerRow.style.justifyContent = "space-between";
            innerRow.appendChild(badge);
            return;
        }

        // ── Fallback: wrap the header content and inject on far right ────────
        const header = document.querySelector("header");
        if (!header) return;
        // Make the header itself a flex row
        header.style.display = "flex";
        header.style.alignItems = "center";
        header.style.justifyContent = "space-between";
        header.appendChild(badge);
    }

})();
