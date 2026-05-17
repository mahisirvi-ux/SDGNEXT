// ==========================================
// MoM Module — Session-Based Minutes of Meeting
// ==========================================

let momState = { sessions: [], activeSession: null, history: [], detailCache: {} };
let momLoaded = false;
let momHtmlCache = "";

function getTpId() {
    return document.getElementById('fd-id').value;
}

// ==========================================
// LOAD SESSIONS
// ==========================================

async function loadMomData(tpId) {
    if (momLoaded) return;
    momLoaded = true;
    await refreshSessions(tpId);
}

async function refreshSessions(tpId) {
    try {
        const res = await fetch(`/api/touchpoints/${tpId}/mom/sessions`);
        const data = await res.json();
        momState.sessions = data.sessions || [];
        momState.activeSession = momState.sessions.find(s => s.status !== 'SENT') || null;
        momState.history = momState.sessions.filter(s => s.status === 'SENT');
        renderMomTab();
    } catch (err) {
        console.error("Failed to load MoM sessions:", err);
    }
}

// ==========================================
// RENDER TAB
// ==========================================

function renderMomTab() {
    const container = document.getElementById('mom-tab-content');
    if (!container) return;

    const tpId = getTpId();
    const active = momState.activeSession;
    const history = momState.history;
    const todayStr = new Date().toISOString().split('T')[0];
    const hasActiveDraft = !!active;
    const todaySent = history.some(s => s.session_date === todayStr);
    const btnDisabled = hasActiveDraft || todaySent;

    let html = '';

    // Header
    html += `<div class="flex items-center justify-between mb-4">
        <h3 class="text-xs font-bold text-[#1a233a] uppercase tracking-wider">MoM Sessions</h3>
        <button onclick="createNewSession()" ${btnDisabled ? 'disabled' : ''} class="text-[10px] font-bold px-3 py-1.5 rounded-md transition-colors ${btnDisabled ? 'bg-slate-100 text-slate-400 cursor-not-allowed' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100'}">
            + New Session for Today
        </button>
    </div>`;

    // Stale draft notice
    if (active && active.session_date !== todayStr) {
        html += `<div class="mb-3 p-2 bg-amber-50 border border-amber-200 rounded-lg text-[10px] text-amber-700">
            You have a <strong>${active.status}</strong> session from <strong>${active.session_date}</strong>. Send or delete it to start a new session.
        </div>`;
    }

    // Active session card
    if (active) {
        html += renderActiveCard(active);
    } else if (history.length === 0) {
        html += `<div class="p-6 text-center border border-dashed border-slate-200 rounded-xl mb-4">
            <p class="text-sm text-slate-400">No MoM sessions yet.</p>
            <p class="text-xs text-slate-300 mt-1">Click "+ New Session for Today" to start capturing.</p>
        </div>`;
    }

    // History
    if (history.length > 0) {
        html += `<div class="mt-5"><label class="text-[10px] font-bold text-slate-400 uppercase mb-2 block">History</label>`;
        html += `<div id="mom-history-accordion" class="space-y-2">`;
        history.forEach(s => {
            html += `<div class="border border-slate-200 rounded-lg overflow-hidden">
                <div class="mom-history-header flex items-center justify-between p-3 bg-slate-50 cursor-pointer hover:bg-slate-100 transition-colors" data-session-id="${s.id}">
                    <div class="flex items-center gap-2">
                        <svg class="mom-chevron w-3 h-3 text-slate-400 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                        <span class="text-[11px] font-bold text-slate-700">${s.session_date}</span>
                        <span class="text-[9px] text-slate-400">${s.sent_at ? 'Sent ' + s.sent_at : ''}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-[9px] bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full font-medium">${s.entry_count} items</span>
                        <span class="text-[9px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-medium">${s.discussion_count} disc</span>
                    </div>
                </div>
                <div class="mom-history-body hidden p-4 border-t border-slate-100" id="mom-hist-body-${s.id}">
                    <p class="text-[10px] text-slate-400 italic">Click to load...</p>
                </div>
            </div>`;
        });
        html += `</div></div>`;
    }

    container.innerHTML = html;

    // If active session exists, load its entries
    if (active) {
        loadActiveSessionData(active.id);
    }

    // Accordion listener (event delegation)
    const accordion = document.getElementById('mom-history-accordion');
    if (accordion) {
        accordion.addEventListener('click', function(e) {
            const header = e.target.closest('.mom-history-header');
            if (!header) return;
            const sessionId = header.dataset.sessionId;
            const body = document.getElementById(`mom-hist-body-${sessionId}`);
            const chevron = header.querySelector('.mom-chevron');
            if (body.classList.contains('hidden')) {
                body.classList.remove('hidden');
                chevron.style.transform = 'rotate(90deg)';
                if (!momState.detailCache[sessionId]) {
                    loadHistoryDetail(sessionId);
                }
            } else {
                body.classList.add('hidden');
                chevron.style.transform = '';
            }
        });
    }
}

function renderActiveCard(session) {
    const statusBadge = session.status === 'GENERATED'
        ? '<span class="text-[9px] bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded-full font-medium">GENERATED</span>'
        : '<span class="text-[9px] bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full font-medium">DRAFT</span>';

    return `<div class="bg-white rounded-xl border border-indigo-200 shadow-sm p-5 mb-4">
        <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
                <span class="text-[11px] font-bold text-[#1a233a]">Session: ${session.session_date}</span>
                ${statusBadge}
            </div>
            <button onclick="deleteActiveSession(${session.id})" class="text-[10px] text-red-400 hover:text-red-600 font-bold">Delete</button>
        </div>

        <!-- Action Items -->
        <div class="mb-4">
            <label class="text-[10px] font-bold text-slate-400 uppercase mb-2 block">Action Items</label>
            <div class="overflow-x-auto">
                <table class="w-full text-xs border border-slate-200 rounded-lg">
                    <thead class="bg-slate-50"><tr>
                        <th class="text-left p-2 border-b border-slate-200 font-bold text-slate-500">Description</th>
                        <th class="text-left p-2 border-b border-slate-200 font-bold text-slate-500">Action Point</th>
                        <th class="text-left p-2 border-b border-slate-200 font-bold text-slate-500">Owner</th>
                        <th class="text-left p-2 border-b border-slate-200 font-bold text-slate-500">Expected Date</th>
                        <th class="p-2 border-b border-slate-200 w-8"></th>
                    </tr></thead>
                    <tbody id="mom-action-body"></tbody>
                </table>
            </div>
            <div class="flex gap-2 mt-2">
                <button onclick="addMomRow()" class="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-3 py-1.5 rounded-md hover:bg-indigo-100 transition-colors">+ Add Row</button>
                <button onclick="saveMomEntries()" class="text-[10px] font-bold text-emerald-600 hover:text-emerald-800 bg-emerald-50 px-3 py-1.5 rounded-md hover:bg-emerald-100 transition-colors">Save Action Items</button>
            </div>
        </div>

        <!-- Discussions -->
        <div class="mb-4">
            <label class="text-[10px] font-bold text-slate-400 uppercase mb-2 block">Discussions</label>
            <div id="mom-discussions-list" class="space-y-2 mb-2"></div>
            <div class="flex gap-2">
                <input type="text" id="mom-new-discussion" class="flex-grow text-xs p-2 rounded-lg border border-slate-200" placeholder="Add discussion point...">
                <button onclick="addDiscussion()" class="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-3 py-1.5 rounded-md hover:bg-indigo-100 transition-colors">+ Add</button>
            </div>
        </div>

        <!-- Buttons -->
        <div class="pt-3 border-t border-slate-100 flex gap-2">
            ${session.status === 'DRAFT' ? `<button onclick="generateMom()" id="btn-generate-mom" class="flex items-center gap-1.5 bg-[#1a233a] hover:bg-[#2d3a54] text-white text-[11px] font-bold py-2 px-4 rounded-lg shadow transition-all">Generate MoM</button>` : ''}
            ${session.status === 'GENERATED' ? `
                <button onclick="generateMom()" class="text-[11px] font-bold text-slate-500 hover:text-slate-700 px-4 py-2 rounded-lg border border-slate-200">Re-generate</button>
                <button onclick="previewAndSend()" class="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-[11px] font-bold py-2 px-4 rounded-lg shadow transition-all">Preview & Send MoM</button>
            ` : ''}
        </div>
    </div>`;
}

// ==========================================
// ACTIVE SESSION DATA
// ==========================================

async function loadActiveSessionData(sessionId) {
    try {
        const [entriesRes, discRes] = await Promise.all([
            fetch(`/api/mom/sessions/${sessionId}/entries`),
            fetch(`/api/mom/sessions/${sessionId}/discussions`)
        ]);
        const entriesData = await entriesRes.json();
        const discData = await discRes.json();
        renderMomRows(entriesData.entries || []);
        renderDiscussions(discData.entries || []);
    } catch (err) {
        console.error("Failed to load active session data:", err);
    }
}

// ==========================================
// HISTORY DETAIL (lazy load)
// ==========================================

async function loadHistoryDetail(sessionId) {
    const tpId = getTpId();
    const body = document.getElementById(`mom-hist-body-${sessionId}`);
    body.innerHTML = '<p class="text-[10px] text-slate-400">Loading...</p>';

    try {
        const res = await fetch(`/api/touchpoints/${tpId}/mom/sessions/${sessionId}`);
        const data = await res.json();
        momState.detailCache[sessionId] = data;

        let html = '';

        // Entries table (read-only)
        if (data.entries && data.entries.length > 0) {
            html += `<label class="text-[9px] font-bold text-slate-400 uppercase mb-1 block">Action Items</label>
            <table class="w-full text-[10px] border border-slate-200 rounded mb-3">
                <thead class="bg-slate-50"><tr>
                    <th class="text-left p-1.5 border-b font-bold text-slate-500">Description</th>
                    <th class="text-left p-1.5 border-b font-bold text-slate-500">Action</th>
                    <th class="text-left p-1.5 border-b font-bold text-slate-500">Owner</th>
                    <th class="text-left p-1.5 border-b font-bold text-slate-500">Due</th>
                </tr></thead><tbody>`;
            data.entries.forEach(e => {
                html += `<tr class="border-b border-slate-50">
                    <td class="p-1.5">${escHtml(e.description)}</td>
                    <td class="p-1.5">${escHtml(e.action_point)}</td>
                    <td class="p-1.5">${escHtml(e.owner_display || e.owner)}</td>
                    <td class="p-1.5">${e.expected_date}</td>
                </tr>`;
            });
            html += `</tbody></table>`;
        }

        // Discussions (read-only)
        if (data.discussions && data.discussions.length > 0) {
            html += `<label class="text-[9px] font-bold text-slate-400 uppercase mb-1 block">Discussions</label>`;
            data.discussions.forEach(d => {
                html += `<div class="text-[10px] text-slate-600 p-1.5 bg-slate-50 rounded mb-1">${escHtml(d.content)} <span class="text-slate-400">(${d.created_at})</span></div>`;
            });
        }

        // View HTML button
        if (data.session && data.session.generated_html) {
            html += `<button onclick="viewHistoryHtml(${sessionId})" class="mt-2 text-[10px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-3 py-1.5 rounded-md">View MoM HTML</button>`;
        }

        body.innerHTML = html || '<p class="text-[10px] text-slate-400 italic">No content in this session.</p>';
    } catch (err) {
        body.innerHTML = '<p class="text-[10px] text-red-400">Failed to load.</p>';
    }
}

function viewHistoryHtml(sessionId) {
    const data = momState.detailCache[sessionId];
    if (!data || !data.session.generated_html) return;
    momHtmlCache = data.session.generated_html;
    document.getElementById('mom-modal-content').innerHTML = momHtmlCache;
    document.getElementById('btn-send-mom').classList.add('hidden');
    document.getElementById('mom-modal').classList.remove('hidden');
}

// ==========================================
// CREATE / DELETE SESSION
// ==========================================

async function createNewSession() {
    const tpId = getTpId();
    try {
        const res = await fetch(`/api/touchpoints/${tpId}/mom/sessions`, {method: 'POST'});
        if (res.status === 201) {
            momLoaded = false;
            momState.detailCache = {};
            await refreshSessions(tpId);
        } else {
            const err = await res.json();
            alert(err.detail || "Cannot create session.");
        }
    } catch (err) {
        alert("Network error creating session.");
    }
}

async function deleteActiveSession(sessionId) {
    if (!confirm("Delete this session and all its entries?")) return;
    const tpId = getTpId();
    try {
        const res = await fetch(`/api/touchpoints/${tpId}/mom/sessions/${sessionId}`, {method: 'DELETE'});
        if (res.ok) {
            momLoaded = false;
            momState.detailCache = {};
            await refreshSessions(tpId);
        } else {
            const err = await res.json();
            alert(err.detail || "Cannot delete.");
        }
    } catch (err) {
        alert("Network error.");
    }
}

// ==========================================
// ACTION ITEMS (within active session)
// ==========================================

function renderMomRows(entries) {
    const tbody = document.getElementById('mom-action-body');
    if (!tbody) return;
    if (entries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="p-3 text-center text-slate-400 text-xs italic">No action items. Click "+ Add Row".</td></tr>';
        return;
    }
    tbody.innerHTML = entries.map(e => `
        <tr class="border-b border-slate-100">
            <td class="p-1.5"><input type="text" class="mom-desc w-full text-xs p-1.5 border border-slate-200 rounded" value="${escHtml(e.description)}"></td>
            <td class="p-1.5"><input type="text" class="mom-action w-full text-xs p-1.5 border border-slate-200 rounded" value="${escHtml(e.action_point)}"></td>
            <td class="p-1.5"><input type="text" class="mom-owner w-full text-xs p-1.5 border border-slate-200 rounded" value="${escHtml(e.owner)}"></td>
            <td class="p-1.5"><input type="date" class="mom-date w-full text-xs p-1.5 border border-slate-200 rounded" value="${e.expected_date}"></td>
            <td class="p-1.5 text-center"><button onclick="removeMomRow(this)" class="text-red-400 hover:text-red-600 text-xs font-bold">&times;</button></td>
        </tr>
    `).join('');
}

function addMomRow() {
    const tbody = document.getElementById('mom-action-body');
    if (!tbody) return;
    if (tbody.querySelector('td[colspan]')) tbody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'border-b border-slate-100';
    row.innerHTML = `
        <td class="p-1.5"><input type="text" class="mom-desc w-full text-xs p-1.5 border border-slate-200 rounded" placeholder="Description"></td>
        <td class="p-1.5"><input type="text" class="mom-action w-full text-xs p-1.5 border border-slate-200 rounded" placeholder="Action point"></td>
        <td class="p-1.5"><input type="text" class="mom-owner w-full text-xs p-1.5 border border-slate-200 rounded" placeholder="Owner"></td>
        <td class="p-1.5"><input type="date" class="mom-date w-full text-xs p-1.5 border border-slate-200 rounded"></td>
        <td class="p-1.5 text-center"><button onclick="removeMomRow(this)" class="text-red-400 hover:text-red-600 text-xs font-bold">&times;</button></td>
    `;
    tbody.appendChild(row);
}

function removeMomRow(btn) { btn.closest('tr').remove(); }

async function saveMomEntries() {
    const sessionId = momState.activeSession?.id;
    if (!sessionId) return;
    const rows = document.querySelectorAll('#mom-action-body tr');
    const items = [];
    rows.forEach(row => {
        const desc = row.querySelector('.mom-desc');
        if (!desc) return;
        items.push({
            description: desc.value, action_point: row.querySelector('.mom-action').value,
            owner: row.querySelector('.mom-owner').value, expected_date: row.querySelector('.mom-date').value
        });
    });

    try {
        const res = await fetch(`/api/mom/sessions/${sessionId}/entries`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({items})
        });
        const data = await res.json();
        if (data.warnings && data.warnings.length > 0) alert("Saved with warnings:\n" + data.warnings.join("\n"));
        renderMomRows(data.entries || []);
    } catch (err) {
        alert("Error saving action items.");
    }
}

// ==========================================
// DISCUSSIONS (within active session)
// ==========================================

let activDiscussions = [];

function renderDiscussions(entries) {
    activDiscussions = entries || [];
    const container = document.getElementById('mom-discussions-list');
    if (!container) return;
    if (activDiscussions.length === 0) {
        container.innerHTML = '<p class="text-xs text-slate-400 italic">No discussions yet.</p>';
        return;
    }
    container.innerHTML = activDiscussions.map(d => `
        <div class="flex items-start gap-2 p-2 bg-slate-50 border border-slate-100 rounded-lg">
            <div class="flex-grow">
                <p class="text-xs text-slate-700">${escHtml(d.content)}</p>
                <p class="text-[9px] text-slate-400 mt-0.5">${d.created_at}</p>
            </div>
            <button onclick="removeDiscussion(${d.id})" class="text-red-400 hover:text-red-600 text-xs font-bold flex-shrink-0">&times;</button>
        </div>
    `).join('');
}

async function addDiscussion() {
    const input = document.getElementById('mom-new-discussion');
    const content = input.value.trim();
    if (!content) return;
    const sessionId = momState.activeSession?.id;
    if (!sessionId) return;

    activDiscussions.push({content: content, created_by: "User", created_at: "Just now"});
    const items = activDiscussions.map(d => ({content: d.content}));

    try {
        const res = await fetch(`/api/mom/sessions/${sessionId}/discussions`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({items})
        });
        const data = await res.json();
        renderDiscussions(data.entries || []);
        input.value = "";
    } catch (err) {
        console.error("Failed to save discussion:", err);
    }
}

async function removeDiscussion(entryId) {
    const sessionId = momState.activeSession?.id;
    if (!sessionId) return;
    try {
        await fetch(`/api/mom/sessions/${sessionId}/discussions/${entryId}`, {method: 'DELETE'});
        activDiscussions = activDiscussions.filter(d => d.id !== entryId);
        renderDiscussions(activDiscussions);
    } catch (err) {
        console.error("Failed to delete discussion:", err);
    }
}

// ==========================================
// GENERATE & SEND
// ==========================================

async function generateMom() {
    const sessionId = momState.activeSession?.id;
    if (!sessionId) return;

    const btn = document.getElementById('btn-generate-mom') || event.target;
    const origText = btn.innerText;
    btn.innerText = "Generating...";
    btn.disabled = true;

    try {
        const res = await fetch(`/api/mom/sessions/${sessionId}/generate`, {method: 'POST'});
        const data = await res.json();
        if (data.html) {
            momHtmlCache = data.html;
            // Refresh state to show GENERATED buttons
            momState.activeSession.status = data.status || 'GENERATED';
            momLoaded = false;
            await refreshSessions(getTpId());
        }
    } catch (err) {
        alert("Error generating MoM.");
    } finally {
        btn.innerText = origText;
        btn.disabled = false;
    }
}

function previewAndSend() {
    const session = momState.activeSession;
    if (!session) return;
    // Use cached html or generated_html from session
    const html = momHtmlCache || session.generated_html || "";
    if (!html) { alert("No generated HTML available. Generate first."); return; }
    document.getElementById('mom-modal-content').innerHTML = html;
    document.getElementById('btn-send-mom').classList.remove('hidden');
    document.getElementById('mom-modal').classList.remove('hidden');
}

function closeMomModal() {
    document.getElementById('mom-modal').classList.add('hidden');
}

async function sendMom() {
    const sessionId = momState.activeSession?.id;
    if (!sessionId) return;

    const btn = document.getElementById('btn-send-mom');
    btn.innerText = "Sending...";
    btn.disabled = true;

    const overrideInput = document.getElementById('mom-override-recipients').value.trim();
    const recipients = overrideInput ? overrideInput.split(',').map(e => e.trim()) : null;

    try {
        const res = await fetch(`/api/mom/sessions/${sessionId}/send`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({html: momHtmlCache, recipients: recipients})
        });
        const data = await res.json();
        if (data.success) {
            alert(`MoM sent to ${data.sent_to.length} recipient(s).`);
            closeMomModal();
            momLoaded = false;
            momState.detailCache = {};
            await refreshSessions(getTpId());
        } else {
            alert("Failed. Skipped: " + (data.skipped || []).join(", "));
        }
    } catch (err) {
        alert("Error sending MoM.");
    } finally {
        btn.innerText = "Send to Stakeholders";
        btn.disabled = false;
    }
}

// ==========================================
// HELPERS
// ==========================================

function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
