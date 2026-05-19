// ==========================================
// Follow-Ups Module
// ==========================================

let fuState = { allItems: [], filteredItems: [], currentFilter: 'OPEN', counts: { open: 0, closed: 0 } };
let fuLoaded = false;
let fuCloseTargetId = null;

function getFuTpId() {
    return document.getElementById('fd-id').value;
}

// ==========================================
// LOAD
// ==========================================

async function loadFollowups(tpId, filter) {
    if (!filter && fuLoaded) {
        renderFollowupsTab();
        return;
    }
    fuLoaded = true;

    try {
        const res = await fetch(`/api/touchpoints/${tpId}/followups?status=ALL`);
        const data = await res.json();
        fuState.allItems = data.items || [];
        fuState.counts.open = fuState.allItems.filter(i => i.status === 'OPEN').length;
        fuState.counts.closed = fuState.allItems.filter(i => i.status === 'CLOSED').length;
        applyFilter(fuState.currentFilter);
    } catch (err) {
        console.error("Failed to load follow-ups:", err);
    }
}

function applyFilter(filter) {
    fuState.currentFilter = filter;
    if (filter === 'OPEN') {
        fuState.filteredItems = fuState.allItems.filter(i => i.status === 'OPEN');
    } else if (filter === 'CLOSED') {
        fuState.filteredItems = fuState.allItems.filter(i => i.status === 'CLOSED');
    } else {
        fuState.filteredItems = [...fuState.allItems];
    }
    renderFollowupsTab();
}

// ==========================================
// RENDER
// ==========================================

function renderFollowupsTab() {
    const container = document.getElementById('followups-container');
    if (!container) return;

    const openCount = fuState.counts.open;
    const closedCount = fuState.counts.closed;
    const allCount = fuState.allItems.length;

        let html = `<div class="flex items-center justify-between mb-4">
        <h3 class="text-xs font-bold text-[#1a233a] uppercase tracking-wider">Follow-Ups</h3>
        <div class="flex items-center gap-2">
            <button onclick="triggerMomNudgeNow(event)" class="text-[10px] font-bold text-purple-600 hover:text-purple-800 bg-purple-50 px-3 py-1.5 rounded-md hover:bg-purple-100 transition-colors border border-purple-200" title="Dev: manually trigger MoM-pointer nudge email for this touchpoint (bypasses throttle)">&#129514; Test MoM Nudge</button>
            <button onclick="openFuAddModal()" class="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-3 py-1.5 rounded-md hover:bg-indigo-100 transition-colors">+ Add Follow-Up</button>
        </div>
    </div>`;

    // Filter bar
    html += `<div class="flex gap-2 mb-4">
        <button onclick="applyFilter('ALL')" class="text-[10px] font-bold px-3 py-1 rounded-full transition-colors ${fuState.currentFilter === 'ALL' ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}">All (${allCount})</button>
        <button onclick="applyFilter('OPEN')" class="text-[10px] font-bold px-3 py-1 rounded-full transition-colors ${fuState.currentFilter === 'OPEN' ? 'bg-amber-500 text-white' : 'bg-amber-50 text-amber-700 hover:bg-amber-100'}">Open (${openCount})</button>
        <button onclick="applyFilter('CLOSED')" class="text-[10px] font-bold px-3 py-1 rounded-full transition-colors ${fuState.currentFilter === 'CLOSED' ? 'bg-emerald-500 text-white' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}">Closed (${closedCount})</button>
    </div>`;

    if (fuState.filteredItems.length === 0) {
        html += `<div class="p-6 text-center border border-dashed border-slate-200 rounded-xl">
            <p class="text-sm text-slate-400">No ${fuState.currentFilter.toLowerCase()} follow-ups.</p>
            <p class="text-xs text-slate-300 mt-1">Send a MoM to generate them, or add one manually.</p>
        </div>`;
    } else {
        html += `<div class="overflow-x-auto"><table class="w-full text-xs border border-slate-200 rounded-lg">
            <thead class="bg-slate-50"><tr>
                <th class="text-left p-2 border-b font-bold text-slate-500 w-6">#</th>
                <th class="text-left p-2 border-b font-bold text-slate-500">Description</th>
                <th class="text-left p-2 border-b font-bold text-slate-500">Action</th>
                <th class="text-left p-2 border-b font-bold text-slate-500">Owner</th>
                <th class="text-left p-2 border-b font-bold text-slate-500">Due</th>
                <th class="text-left p-2 border-b font-bold text-slate-500">Status</th>
                <th class="text-left p-2 border-b font-bold text-slate-500">Source</th>
            </tr></thead><tbody id="fu-table-body">`;

        fuState.filteredItems.forEach((item, idx) => {
            const statusPill = item.status === 'CLOSED'
                ? '<span class="text-[9px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">CLOSED</span>'
                : item.is_overdue
                    ? '<span class="text-[9px] bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium">OVERDUE</span>'
                    : '<span class="text-[9px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-medium">OPEN</span>';

            const source = item.source_mom_entry_id
                ? `<span class="text-[9px] text-indigo-500">MoM ${item.source_session_date || ''}</span>`
                : '<span class="text-[9px] text-slate-400">Manual</span>';

            const actionBtns = item.status === 'OPEN'
                ? `<button class="fu-status-btn text-[9px] text-emerald-600 hover:text-emerald-800 underline ml-1" data-id="${item.id}" data-action="close">Close</button>`
                : `<button class="fu-status-btn text-[9px] text-amber-600 hover:text-amber-800 underline ml-1" data-id="${item.id}" data-action="reopen">Reopen</button>`;

            const deleteBtn = !item.source_mom_entry_id
                ? `<button class="fu-status-btn text-[9px] text-red-400 hover:text-red-600 ml-1" data-id="${item.id}" data-action="delete">&times;</button>`
                : '';

            html += `<tr class="border-b border-slate-50 hover:bg-slate-50/50">
                <td class="p-2 text-slate-400">${idx + 1}</td>
                <td class="p-2">${fuEsc(item.description)}</td>
                <td class="p-2 text-slate-500">${fuEsc(item.action)}</td>
                <td class="p-2">${fuEsc(item.owner_display || item.owner)}</td>
                <td class="p-2 ${item.is_overdue ? 'text-red-600 font-bold' : ''}">${item.due_date || '—'}</td>
                <td class="p-2">${statusPill} ${actionBtns}</td>
                <td class="p-2">${source} ${deleteBtn}</td>
            </tr>`;
        });

        html += `</tbody></table></div>`;
    }

    container.innerHTML = html;

    // Event delegation for status/action buttons
    const tbody = document.getElementById('fu-table-body');
    if (tbody) {
        tbody.addEventListener('click', function(e) {
            const btn = e.target.closest('.fu-status-btn');
            if (!btn) return;
            const itemId = btn.dataset.id;
            const action = btn.dataset.action;
            if (action === 'close') openFuCloseModal(itemId);
            else if (action === 'reopen') reopenFollowup(itemId);
            else if (action === 'delete') deleteFollowup(itemId);
        });
    }
}

// ==========================================
// ADD FOLLOW-UP
// ==========================================

function openFuAddModal() {
    document.getElementById('fu-add-desc').value = '';
    document.getElementById('fu-add-action').value = '';
    document.getElementById('fu-add-owner').value = '';
    document.getElementById('fu-add-due').value = '';
    document.getElementById('fu-add-modal').classList.remove('hidden');
}

function closeFuAddModal() {
    document.getElementById('fu-add-modal').classList.add('hidden');
}

async function submitNewFollowup() {
    const tpId = getFuTpId();
    const desc = document.getElementById('fu-add-desc').value.trim();
    if (!desc) { alert("Description is required."); return; }

    const payload = {
        description: desc,
        action: document.getElementById('fu-add-action').value.trim(),
        owner: document.getElementById('fu-add-owner').value.trim(),
        due_date: document.getElementById('fu-add-due').value
    };

    try {
        const res = await fetch(`/api/touchpoints/${tpId}/followups`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.warnings && data.warnings.length > 0) {
            alert("Created with warnings:\n" + data.warnings.join("\n"));
        }
        closeFuAddModal();
        fuLoaded = false;
        loadFollowups(tpId, true);
    } catch (err) {
        alert("Error creating follow-up.");
    }
}

// ==========================================
// CLOSE / REOPEN / DELETE
// ==========================================

function openFuCloseModal(itemId) {
    fuCloseTargetId = itemId;
    document.getElementById('fu-close-note').value = '';
    document.getElementById('fu-close-modal').classList.remove('hidden');
}

function closeFuCloseModal() {
    document.getElementById('fu-close-modal').classList.add('hidden');
    fuCloseTargetId = null;
}

async function confirmCloseFollowup() {
    if (!fuCloseTargetId) return;
    const tpId = getFuTpId();
    const note = document.getElementById('fu-close-note').value.trim();

    try {
        const res = await fetch(`/api/touchpoints/${tpId}/followups/${fuCloseTargetId}/close`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({close_note: note})
        });
        if (res.ok) {
            closeFuCloseModal();
            fuLoaded = false;
            loadFollowups(tpId, true);
        } else {
            const err = await res.json();
            alert(err.detail || "Failed to close.");
        }
    } catch (err) {
        alert("Network error.");
    }
}

async function reopenFollowup(itemId) {
    const tpId = getFuTpId();
    try {
        const res = await fetch(`/api/touchpoints/${tpId}/followups/${itemId}/reopen`, {method: 'POST'});
        if (res.ok) {
            fuLoaded = false;
            loadFollowups(tpId, true);
        } else {
            const err = await res.json();
            alert(err.detail || "Failed to reopen.");
        }
    } catch (err) {
        alert("Network error.");
    }
}

async function deleteFollowup(itemId) {
    if (!confirm("Delete this follow-up?")) return;
    const tpId = getFuTpId();
    try {
        const res = await fetch(`/api/touchpoints/${tpId}/followups/${itemId}`, {method: 'DELETE'});
        if (res.ok) {
            fuLoaded = false;
            loadFollowups(tpId, true);
        } else {
            const err = await res.json();
            alert(err.detail || "Cannot delete.");
        }
    } catch (err) {
        alert("Network error.");
    }
}

// ==========================================
// DEV: MANUAL MOM-POINTER NUDGE
// ==========================================

async function triggerMomNudgeNow(event) {
    const tpId = getFuTpId();
    if (!tpId) {
        alert("Touchpoint context not loaded.");
        return;
    }

    if (!confirm("Send MoM-pointer nudge now?\n\n" +
        "This will email the touchpoint's open MoM-spawned follow-ups " +
        "to the resolved recipients, threaded on the original MoM email. " +
        "Throttle is bypassed for testing.")) {
        return;
    }

    const btn = event.currentTarget;
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "Sending...";

    try {
        const resp = await fetch(`/api/touchpoints/${tpId}/mom-nudge-now`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const data = await resp.json();

        if (data.sent) {
            const extra = data.reason === "no_anchor_sent_anyway"
                ? "\n(Sent without threading — no MoM with MSG_ID exists yet.)"
                : "";
            alert(`\u2713 MoM nudge sent for ${data.items_count} open item(s). ` +
                  `Check the recipient inbox.${extra}`);
        } else {
            const reasonLabels = {
                "no_items": "No open MoM-spawned follow-ups for this touchpoint.",
                "all_throttled": "All items throttled (should not happen with force=true).",
                "no_recipients": "No recipients could be resolved. Check pending-with and owner fields.",
                "send_failed": `Send failed: ${data.error || "SMTP error"}`
            };
            const msg = reasonLabels[data.reason] || data.reason;
            alert(`MoM nudge: ${msg}`);
        }
    } catch (err) {
        alert("Network or server error: " + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// ==========================================
// HELPERS
// ==========================================

function fuEsc(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
