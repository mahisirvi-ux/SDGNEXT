/**
 * js/kb.js  —  Knowledge Base page logic
 * Handles: category nav, article list, article reader, create/edit modal, search
 */

// ── State ────────────────────────────────────────────────────────────────────
const kbState = {
    categories:    [],
    articles:      [],          // full list for current filter
    activeCat:     null,        // null = All
    searchQuery:   "",
    currentArticle: null,       // article object shown in reader
    editingId:     null,        // article id being edited (null = create)
    tags:          [],          // tags in modal
    userRole:      "viewer",    // set from SDGAuth
};

// ── Colour map ────────────────────────────────────────────────────────────────
const COLOR_MAP = {
    blue:   { bg: "bg-blue-50",   text: "text-blue-600",   border: "border-blue-200"  },
    indigo: { bg: "bg-indigo-50", text: "text-indigo-600", border: "border-indigo-200"},
    teal:   { bg: "bg-teal-50",   text: "text-teal-600",   border: "border-teal-200"  },
    amber:  { bg: "bg-amber-50",  text: "text-amber-600",  border: "border-amber-200" },
    pink:   { bg: "bg-pink-50",   text: "text-pink-600",   border: "border-pink-200"  },
};
function colorFor(color) { return COLOR_MAP[color] || COLOR_MAP.indigo; }

// ── Category icons (inline SVG paths) ─────────────────────────────────────────
const CAT_ICON = {
    guide:   `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>`,
    api:     `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/>`,
    sop:     `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/>`,
    faq:     `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>`,
    release: `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"/>`,
    book:    `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/>`,
};
function iconSVG(key) {
    return `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">${CAT_ICON[key] || CAT_ICON.book}</svg>`;
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // Resolve role from auth
    const u = window.SDGAuth?.user;
    kbState.userRole = u?.role || "viewer";

    // Show admin-only UI
    if (["admin", "manager"].includes(kbState.userRole)) {
        document.getElementById("kb-admin-actions").classList.remove("hidden");
        document.getElementById("kb-header-new-btn").classList.remove("hidden");
        if (kbState.userRole === "admin") {
            document.getElementById("modal-admin-flags").classList.remove("hidden");
        }
    }

    // Handle ?article=<id> deep-link
    const params = new URLSearchParams(window.location.search);
    const articleId = params.get("article");

    await loadCategories();
    await loadArticles();

    if (articleId) openReader(parseInt(articleId));
});

// ── Data fetching ─────────────────────────────────────────────────────────────
async function loadCategories() {
    try {
        const res  = await fetch("/api/kb/categories");
        const data = await res.json();
        kbState.categories = data.categories || [];
        renderCatNav();
        populateModalCategories();
    } catch (e) { console.error("KB categories failed:", e); }
}

async function loadArticles(catId = null) {
    const url = catId
        ? `/api/kb/articles?category_id=${catId}&limit=50`
        : `/api/kb/articles?limit=50`;
    try {
        const res  = await fetch(url);
        const data = await res.json();
        kbState.articles = data.articles || [];
        renderArticleList();
    } catch (e) { console.error("KB articles failed:", e); }
}

// ── Category nav ──────────────────────────────────────────────────────────────
function renderCatNav() {
    const nav   = document.getElementById("kb-cat-nav");
    const total = kbState.categories.reduce((s, c) => s + c.article_count, 0);

    const allActive = kbState.activeCat === null;
    let html = `
        <button class="cat-nav-item w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs ${allActive ? "active" : "text-slate-600"}"
                onclick="selectCategory(null)">
            <span class="flex items-center gap-2">
                ${iconSVG("book")}
                All Articles
            </span>
            <span class="text-[10px] font-bold ${allActive ? "text-indigo-400" : "text-slate-400"}">${total}</span>
        </button>`;

    kbState.categories.forEach(c => {
        const col    = colorFor(c.color);
        const active = kbState.activeCat === c.id;
        html += `
            <button class="cat-nav-item w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs ${active ? "active" : "text-slate-600"}"
                    onclick="selectCategory(${c.id})">
                <span class="flex items-center gap-2">
                    ${iconSVG(c.icon)}
                    ${escHtml(c.name)}
                </span>
                <span class="text-[10px] font-bold ${active ? "text-indigo-400" : "text-slate-400"}">${c.article_count}</span>
            </button>`;
    });

    nav.innerHTML = html;
}

function selectCategory(catId) {
    kbState.activeCat  = catId;
    kbState.searchQuery = "";
    document.getElementById("kb-search").value = "";
    closeReader();
    renderCatNav();

    // Update header title
    const cat = kbState.categories.find(c => c.id === catId);
    document.getElementById("kb-list-title").textContent = cat ? cat.name : "All Articles";

    loadArticles(catId);
}

// ── Article list ──────────────────────────────────────────────────────────────
function renderArticleList() {
    const pinned    = kbState.articles.filter(a => a.is_pinned);
    const unpinned  = kbState.articles.filter(a => !a.is_pinned);

    const pinnedSec = document.getElementById("kb-pinned-section");
    const pinnedList= document.getElementById("kb-pinned-list");
    const grid      = document.getElementById("kb-articles-grid");
    const empty     = document.getElementById("kb-empty");
    const subtitle  = document.getElementById("kb-list-subtitle");

    subtitle.textContent = `${kbState.articles.length} article${kbState.articles.length !== 1 ? "s" : ""}`;

    if (kbState.articles.length === 0) {
        pinnedSec.classList.add("hidden");
        grid.innerHTML = "";
        empty.classList.remove("hidden");
        return;
    }
    empty.classList.add("hidden");

    // Pinned
    if (pinned.length && !kbState.activeCat) {
        pinnedSec.classList.remove("hidden");
        pinnedList.innerHTML = pinned.map(a => renderPinnedCard(a)).join("");
    } else {
        pinnedSec.classList.add("hidden");
    }

    // Grid
    grid.innerHTML = unpinned.map(a => renderArticleCard(a)).join("");
}

function renderPinnedCard(a) {
    const col = colorFor(a.category_color);
    return `
        <div class="article-card bg-white border border-slate-200 rounded-xl p-5 flex gap-4"
             onclick="openReader(${a.id})">
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-2">
                    <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${col.bg} ${col.text}">${escHtml(a.category_name)}</span>
                    <svg class="w-3 h-3 text-amber-400 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M16 1v6l2 3v3H6V10l2-3V1h8zm-5 20a2 2 0 0 0 4 0H11z"/></svg>
                </div>
                <h4 class="text-sm font-bold text-[#1a233a] mb-1">${escHtml(a.title)}</h4>
                <p class="text-xs text-slate-500 leading-relaxed line-clamp-2">${escHtml(a.summary)}</p>
                <div class="flex items-center gap-3 mt-3">
                    ${a.tags.slice(0, 3).map(t => `<span class="tag-pill">#${escHtml(t)}</span>`).join("")}
                    <span class="text-[10px] text-slate-400 ml-auto">${a.view_count} views</span>
                </div>
            </div>
        </div>`;
}

function renderArticleCard(a) {
    const col  = colorFor(a.category_color);
    const date = fmtDate(a.updated_at);
    return `
        <div class="article-card bg-white border border-slate-200 rounded-xl p-5"
             onclick="openReader(${a.id})">
            <div class="flex items-center gap-2 mb-3">
                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${col.bg} ${col.text}">${escHtml(a.category_name)}</span>
                ${!a.is_published ? `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">Draft</span>` : ""}
            </div>
            <h4 class="text-sm font-bold text-[#1a233a] mb-1.5 leading-snug">${escHtml(a.title)}</h4>
            <p class="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-3">${escHtml(a.summary)}</p>
            <div class="flex items-center justify-between">
                <div class="flex gap-1.5">${a.tags.slice(0, 2).map(t => `<span class="tag-pill">#${escHtml(t)}</span>`).join("")}</div>
                <span class="text-[10px] text-slate-400">${date}</span>
            </div>
        </div>`;
}

// ── Article reader ────────────────────────────────────────────────────────────
async function openReader(articleId) {
    // Show skeleton immediately
    document.getElementById("kb-list-view").classList.add("hidden");
    const reader = document.getElementById("kb-reader-view");
    reader.classList.remove("hidden");
    reader.innerHTML = renderReaderSkeleton();

    try {
        const res  = await fetch(`/api/kb/articles/${articleId}`);
        if (!res.ok) throw new Error("Not found");
        const a    = await res.json();
        kbState.currentArticle = a;

        // Re-render full reader
        reader.innerHTML = readerTemplate();
        renderReaderContent(a);
    } catch (e) {
        reader.innerHTML = `<p class="text-sm text-red-500 mt-10">Could not load article.</p>`;
    }
}

function readerTemplate() {
    return `
        <button onclick="closeReader()" class="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-[#1a233a] mb-5 transition-colors">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
            Back to Knowledge Base
        </button>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8 max-w-3xl">
            <div class="flex items-center gap-2 mb-4" id="reader-meta-top"></div>
            <h1 id="reader-title" class="text-2xl font-black text-[#1a233a] leading-tight mb-2"></h1>
            <div class="flex items-center gap-3 text-xs text-slate-400 mb-1" id="reader-meta-bottom"></div>
            <div id="reader-tags" class="flex flex-wrap gap-1.5 mb-6 mt-3"></div>
            <hr class="border-slate-100 mb-6">
            <div id="reader-body" class="kb-prose"></div>
            <div id="reader-admin-actions" class="hidden mt-8 pt-5 border-t border-slate-100 flex items-center gap-2">
                <button id="reader-edit-btn" onclick="editCurrentArticle()" class="text-xs font-bold text-indigo-600 border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-lg transition-colors">Edit</button>
                <button id="reader-publish-btn" onclick="togglePublishCurrentArticle()" class="text-xs font-bold px-4 py-2 rounded-lg transition-colors border"></button>
                <button id="reader-delete-btn" onclick="deleteCurrentArticle()" class="text-xs font-bold text-red-500 border border-red-100 bg-red-50 hover:bg-red-100 px-4 py-2 rounded-lg transition-colors ml-auto">Delete</button>
            </div>
        </div>`;
}

function renderReaderContent(a) {
    const col = colorFor(a.category_color);

    // Top meta
    document.getElementById("reader-meta-top").innerHTML = `
        <span class="text-[11px] font-bold px-2.5 py-1 rounded-full ${col.bg} ${col.text}">${escHtml(a.category_name)}</span>
        ${a.is_pinned ? `<svg class="w-3.5 h-3.5 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M16 1v6l2 3v3H6V10l2-3V1h8zm-5 20a2 2 0 0 0 4 0H11z"/></svg>` : ""}
        ${!a.is_published ? `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-400">Draft</span>` : ""}`;

    document.getElementById("reader-title").textContent = a.title;

    document.getElementById("reader-meta-bottom").innerHTML = `
        <span>By ${escHtml(a.created_by)}</span>
        <span>·</span>
        <span>${fmtDate(a.updated_at)}</span>
        <span>·</span>
        <span>${a.view_count.toLocaleString()} views</span>`;

    document.getElementById("reader-tags").innerHTML =
        (a.tags || []).map(t => `<span class="tag-pill">#${escHtml(t)}</span>`).join("");

    document.getElementById("reader-body").innerHTML = a.body;

    // Admin actions
    if (["admin", "manager"].includes(kbState.userRole)) {
        const adminDiv = document.getElementById("reader-admin-actions");
        adminDiv.classList.remove("hidden");
        const pubBtn = document.getElementById("reader-publish-btn");
        if (kbState.userRole === "admin") {
            pubBtn.textContent    = a.is_published ? "Unpublish" : "Publish";
            pubBtn.className      = `text-xs font-bold px-4 py-2 rounded-lg transition-colors border ${
                a.is_published
                    ? "text-amber-600 border-amber-200 bg-amber-50 hover:bg-amber-100"
                    : "text-emerald-600 border-emerald-200 bg-emerald-50 hover:bg-emerald-100"
            }`;
            document.getElementById("reader-delete-btn").classList.remove("hidden");
        } else {
            // Manager: edit only, no publish/delete
            pubBtn.classList.add("hidden");
            document.getElementById("reader-delete-btn").classList.add("hidden");
        }
    }
}

function renderReaderSkeleton() {
    return `
        <div class="h-4 w-20 skeleton mb-5"></div>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8 max-w-3xl space-y-4">
            <div class="h-3 w-24 skeleton"></div>
            <div class="h-8 w-3/4 skeleton"></div>
            <div class="h-3 w-48 skeleton"></div>
            <div class="h-px bg-slate-100 my-4"></div>
            ${Array(6).fill(`<div class="h-3 skeleton"></div>`).join("")}
        </div>`;
}

function closeReader() {
    kbState.currentArticle = null;
    document.getElementById("kb-reader-view").classList.add("hidden");
    document.getElementById("kb-list-view").classList.remove("hidden");
    // Restore proper reader HTML for next open
    document.getElementById("kb-reader-view").innerHTML = ``;
}

// ── Search ────────────────────────────────────────────────────────────────────
let _searchTimer;
function handleSearch(q) {
    kbState.searchQuery = q.trim();
    clearTimeout(_searchTimer);
    if (!q.trim()) {
        loadArticles(kbState.activeCat);
        return;
    }
    _searchTimer = setTimeout(async () => {
        try {
            const res  = await fetch(`/api/kb/search?q=${encodeURIComponent(q.trim())}`);
            const data = await res.json();
            kbState.articles = data.results || [];
            document.getElementById("kb-list-title").textContent = `Results for "${q.trim()}"`;
            closeReader();
            renderArticleList();
        } catch (e) { console.error(e); }
    }, 300);
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openArticleModal(articleData = null) {
    kbState.editingId = articleData ? articleData.id : null;
    kbState.tags      = articleData ? [...(articleData.tags || [])] : [];

    document.getElementById("modal-title").textContent = articleData ? "Edit Article" : "New Article";
    document.getElementById("modal-article-title").value  = articleData?.title   || "";
    document.getElementById("modal-summary").value        = articleData?.summary || "";
    document.getElementById("rte-editor").innerHTML       = articleData?.body    || "";
    document.getElementById("modal-error").classList.add("hidden");
    document.getElementById("modal-save-label").textContent = "Save Article";
    document.getElementById("modal-save-btn").disabled    = false;

    if (kbState.userRole === "admin") {
        document.getElementById("modal-pinned").checked    = articleData?.is_pinned    ?? false;
        document.getElementById("modal-published").checked = articleData?.is_published ?? true;
    }

    // Set category
    if (articleData?.category_id) {
        document.getElementById("modal-category").value = articleData.category_id;
    } else {
        document.getElementById("modal-category").value = "";
    }

    renderTagPills();
    document.getElementById("kb-article-modal").classList.remove("hidden");
    setTimeout(() => document.getElementById("modal-article-title").focus(), 100);
}

function closeArticleModal() {
    document.getElementById("kb-article-modal").classList.add("hidden");
    kbState.editingId = null;
    kbState.tags      = [];
}

function editCurrentArticle() {
    if (kbState.currentArticle) openArticleModal(kbState.currentArticle);
}

function populateModalCategories() {
    const sel = document.getElementById("modal-category");
    sel.innerHTML = `<option value="">Select category…</option>` +
        kbState.categories.map(c =>
            `<option value="${c.id}">${escHtml(c.name)}</option>`
        ).join("");
}

async function saveArticle() {
    const title       = document.getElementById("modal-article-title").value.trim();
    const summary     = document.getElementById("modal-summary").value.trim();
    const body        = document.getElementById("rte-editor").innerHTML.trim();
    const category_id = parseInt(document.getElementById("modal-category").value);
    const errorEl     = document.getElementById("modal-error");
    const saveBtn     = document.getElementById("modal-save-btn");
    const saveLabel   = document.getElementById("modal-save-label");

    // Validation
    if (!title)       { showModalError("Title is required."); return; }
    if (!category_id) { showModalError("Please select a category."); return; }
    if (!body || body === "<br>") { showModalError("Article body cannot be empty."); return; }

    errorEl.classList.add("hidden");
    saveBtn.disabled      = true;
    saveLabel.textContent = "Saving…";

    const payload = { category_id, title, summary, body, tags: kbState.tags };
    if (kbState.userRole === "admin") {
        payload.is_pinned    = document.getElementById("modal-pinned").checked;
        payload.is_published = document.getElementById("modal-published").checked;
    }

    try {
        const isEdit = !!kbState.editingId;
        const url    = isEdit ? `/api/kb/articles/${kbState.editingId}` : `/api/kb/articles`;
        const res    = await fetch(url, {
            method:  isEdit ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(payload),
        });
        const data   = await res.json();

        if (!res.ok) { showModalError(data.detail || "Save failed."); saveBtn.disabled = false; saveLabel.textContent = "Save Article"; return; }

        closeArticleModal();
        await loadCategories();
        await loadArticles(kbState.activeCat);

        // If editing current article, refresh reader
        if (isEdit && kbState.currentArticle?.id === kbState.editingId) {
            kbState.currentArticle = data.article;
            document.getElementById("kb-list-view").classList.add("hidden");
            document.getElementById("kb-reader-view").classList.remove("hidden");
            document.getElementById("kb-reader-view").innerHTML = readerTemplate();
            renderReaderContent(data.article);
        }
    } catch (e) {
        showModalError("Network error. Please try again.");
        saveBtn.disabled = false; saveLabel.textContent = "Save Article";
    }
}

function showModalError(msg) {
    const el = document.getElementById("modal-error");
    el.textContent = msg;
    el.classList.remove("hidden");
}

// ── Publish toggle ────────────────────────────────────────────────────────────
async function togglePublishCurrentArticle() {
    const a = kbState.currentArticle;
    if (!a) return;
    try {
        const res  = await fetch(`/api/kb/articles/${a.id}/publish`, { method: "PUT" });
        const data = await res.json();
        kbState.currentArticle.is_published = data.is_published;
        document.getElementById("kb-reader-view").innerHTML = readerTemplate();
        renderReaderContent(kbState.currentArticle);
        await loadCategories();
        await loadArticles(kbState.activeCat);
    } catch (e) { alert("Could not toggle publish status."); }
}

// ── Delete ─────────────────────────────────────────────────────────────────────
async function deleteCurrentArticle() {
    const a = kbState.currentArticle;
    if (!a) return;
    if (!confirm(`Delete "${a.title}"? This cannot be undone.`)) return;
    try {
        await fetch(`/api/kb/articles/${a.id}`, { method: "DELETE" });
        closeReader();
        await loadCategories();
        await loadArticles(kbState.activeCat);
    } catch (e) { alert("Could not delete article."); }
}

// ── Rich text editor ──────────────────────────────────────────────────────────
function rte(cmd) {
    document.getElementById("rte-editor").focus();
    document.execCommand(cmd, false, null);
}

function rteHeading(tag) {
    document.getElementById("rte-editor").focus();
    document.execCommand("formatBlock", false, tag);
}

function rteCode() {
    const sel = window.getSelection();
    if (!sel.rangeCount) return;
    const range = sel.getRangeAt(0);
    const code  = document.createElement("code");
    code.textContent = range.toString() || "code";
    range.deleteContents();
    range.insertNode(code);
}

// ── Tags input ────────────────────────────────────────────────────────────────
function handleTagInput(e) {
    const input = document.getElementById("tag-input");
    if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        const val = input.value.trim().replace(/,/g, "");
        if (val && !kbState.tags.includes(val)) {
            kbState.tags.push(val);
            renderTagPills();
        }
        input.value = "";
    } else if (e.key === "Backspace" && !input.value && kbState.tags.length) {
        kbState.tags.pop();
        renderTagPills();
    }
}

function removeTag(tag) {
    kbState.tags = kbState.tags.filter(t => t !== tag);
    renderTagPills();
}

function renderTagPills() {
    const container = document.getElementById("tag-container");
    const input     = document.getElementById("tag-input");
    // Remove old pills
    container.querySelectorAll(".modal-tag-pill").forEach(el => el.remove());
    // Insert before input
    kbState.tags.forEach(tag => {
        const pill = document.createElement("span");
        pill.className = "modal-tag-pill tag-pill";
        pill.innerHTML = `${escHtml(tag)} <button onclick="removeTag('${escHtml(tag)}')" class="ml-1 text-slate-400 hover:text-slate-600">×</button>`;
        container.insertBefore(pill, input);
    });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtDate(isoStr) {
    if (!isoStr) return "";
    try {
        return new Date(isoStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch { return ""; }
}
