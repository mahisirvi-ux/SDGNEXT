let currentData = null;

// ==========================================
// TAB SWITCHING
// ==========================================
function switchTab(tabName) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(t => {
        t.classList.remove('pill-active');
        t.classList.add('pill-inactive');
    });
    const panel = document.getElementById(`panel-${tabName}`);
    if (panel) panel.classList.remove('hidden');
    const tab = document.getElementById(`tab-${tabName}`);
    if (tab) {
        tab.classList.remove('pill-inactive');
        tab.classList.add('pill-active');
    }
        // Lazy-load MoM data on first tab visit
    if (tabName === 'mom' && typeof loadMomData === 'function') {
        const tpId = document.getElementById('fd-id').value;
        if (tpId) loadMomData(tpId);
    }
    // Lazy-load Follow-Ups on first tab visit
    if (tabName === 'followups' && typeof loadFollowups === 'function') {
        const tpId = document.getElementById('fd-id').value;
        if (tpId) loadFollowups(tpId);
    }
}

// ==========================================
// DATA LOADING
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const id = urlParams.get('id');
    if (!id) { alert("No Touchpoint ID provided."); window.location.href = "/"; return; }

    try {
        const response = await fetch(`/api/phase2/touchpoint/${id}`);
        const result = await response.json();
        if (response.ok && result.status === "success") {
            currentData = result.data;
            populatePage(currentData);
        } else {
            alert("Error: " + (result.message || "Unknown error"));
            window.location.href = "/";
        }
    } catch (err) {
        console.error(err);
        alert("Network Error. Ensure backend is running.");
    }
});

// ==========================================
// POPULATE PAGE
// ==========================================
function populatePage(tp) {
    document.getElementById('fd-id').value = tp.id;
    document.getElementById('fd-integration-type').value = tp.integration || 'unassigned';

    // Header
    document.getElementById('fd-name').innerText = tp.name;

    // Key Info Strip
        document.getElementById('fd-strip-module').innerText = tp.module || '-';
    document.getElementById('fd-strip-source').innerText = tp.source || '-';
    document.getElementById('fd-strip-target').innerText = tp.target || '-';
    document.getElementById('fd-strip-integration').innerText = (tp.integration || 'Unassigned').toUpperCase();

    // Basic Info: Profile fields
    document.getElementById('fd-val-flow').innerText = tp.business_flow || '-';
    document.getElementById('fd-val-owner').innerText = tp.owner || '-';
    document.getElementById('fd-val-tech-owner').innerText = tp.tech_owner_name || '-';
    document.getElementById('fd-val-mod-owner').innerText = tp.mod_owner || '-';
    document.getElementById('fd-val-fallback').innerText = tp.fallback || 'None';

    // Left Panel: Schedule
    const rawStart = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start : "";
    const rawEnd = (tp.end && tp.end !== "-" && tp.end !== "None") ? tp.end : "";
    const [sDate = "", sTime = ""] = rawStart.split(" ");
    const [eDate = "", eTime = ""] = rawEnd.split(" ");
    document.getElementById('fd-start').value = sDate;
    document.getElementById('fd-start-time').value = sTime;
    document.getElementById('fd-end').value = eDate;
    document.getElementById('fd-end-time').value = eTime;

    const td = tp.techDetails || {};
    setVal('fd-criticality', td.criticality || "Medium");
    setVal('fd-effort', td.effort || "");
    setVal('fd-attendees', td.attendees || "");

    // Status & Pending With
    setVal('fd-tech-status', tp.techStatus || "Pending Workshop");
    setVal('fd-pending-with', tp.pendingWith || td.pendingWith || "");

    // Workshop Planning Timeline
    const wsStatus = td.workshopStage || determineWorkshopStage(tp);
    updateWorkshopTimeline(wsStatus, tp);

        // Load attachments
        loadDocuments(tp.id);

    // API fields (only set if element exists)
    const intType = (tp.integration || "").toLowerCase();
    if (intType === 'api') {
        // Basic Info
        setVal('fd-api-name', td.apiName || tp.name || "");
        setVal('fd-api-type', td.apiType || "");

        // Connectivity
        setVal('fd-api-endpoint-url', td.endpointUrl || "");
        setVal('fd-api-uat-url', td.uatUrl || "");
        setVal('fd-api-prod-url', td.prodUrl || "");
        setVal('fd-api-method', td.apiMethod || "");
        setVal('fd-api-ip-whitelist', td.ipWhitelist || "");
        setVal('fd-api-vpn', td.vpnRequired || "");

        // Security
        setVal('fd-api-auth', td.apiAuth || "");
        setVal('fd-api-auth-details', td.authDetails || "");
        setVal('fd-api-headers', td.mandatoryHeaders || "");
        setVal('fd-api-cert-notes', td.certNotes || "");

        // Payload
        setVal('fd-api-req', td.apiReq || "");
        setVal('fd-api-res', td.apiRes || "");

        // Error Handling
        setVal('fd-api-error', td.errorSample || "");
        setVal('fd-api-timeout', td.timeout || "");
        setVal('fd-api-tps', td.rateLimitTps || "");
        setVal('fd-api-retry', td.retryMechanism || "");
        setVal('fd-api-callback', td.callbackRequired || "");
        setVal('fd-api-correlation', td.correlationId || "");

        // Documentation
        setVal('fd-api-swagger', td.swaggerUrl || "");
        setVal('fd-api-doc-notes', td.docNotes || "");
    }
}

// Helper: safely set value on an element
function setVal(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

// Helper: safely get value from an element
function getVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : "";
}

// ==========================================
// EDIT MODE
// ==========================================
function toggleDetailsEditMode() {
    document.querySelectorAll('input, textarea, select').forEach(el => {
        if (el.type !== 'hidden') el.disabled = false;
    });
    document.getElementById('fd-btn-edit').classList.add('hidden');
    document.getElementById('fd-btn-save').classList.remove('hidden');
}

// ==========================================
// SAVE
// ==========================================
async function saveFullDetails() {
    const id = document.getElementById('fd-id').value;
    const intType = document.getElementById('fd-integration-type').value.toLowerCase();
    const saveBtn = document.getElementById('fd-btn-save');
    saveBtn.innerText = "Saving...";

        const techDetails = {
        criticality: getVal('fd-criticality'),
        effort: getVal('fd-effort'),
        attendees: getVal('fd-attendees'),
        pendingWith: getVal('fd-pending-with')
    };

    if (intType === 'api') {
        // Basic Info
        techDetails.apiName = getVal('fd-api-name');
        techDetails.apiType = getVal('fd-api-type');
        // Connectivity
        techDetails.endpointUrl = getVal('fd-api-endpoint-url');
        techDetails.uatUrl = getVal('fd-api-uat-url');
        techDetails.prodUrl = getVal('fd-api-prod-url');
        techDetails.apiMethod = getVal('fd-api-method');
        techDetails.ipWhitelist = getVal('fd-api-ip-whitelist');
        techDetails.vpnRequired = getVal('fd-api-vpn');
        // Security
        techDetails.apiAuth = getVal('fd-api-auth');
        techDetails.authDetails = getVal('fd-api-auth-details');
        techDetails.mandatoryHeaders = getVal('fd-api-headers');
        techDetails.certNotes = getVal('fd-api-cert-notes');
        // Payload
        techDetails.apiReq = getVal('fd-api-req');
        techDetails.apiRes = getVal('fd-api-res');
        // Error Handling
        techDetails.errorSample = getVal('fd-api-error');
        techDetails.timeout = getVal('fd-api-timeout');
        techDetails.rateLimitTps = getVal('fd-api-tps');
        techDetails.retryMechanism = getVal('fd-api-retry');
        techDetails.callbackRequired = getVal('fd-api-callback');
        techDetails.correlationId = getVal('fd-api-correlation');
        // Documentation
        techDetails.swaggerUrl = getVal('fd-api-swagger');
        techDetails.docNotes = getVal('fd-api-doc-notes');
        // Timestamp
        techDetails.lastUpdated = new Date().toISOString().split('T')[0];
    }

    const combineDT = (dateId, timeId) => {
        const d = (document.getElementById(dateId)?.value || "").trim();
        if (!d) return "";
        const t = (document.getElementById(timeId)?.value || "").trim() || "00:00";
        return `${d} ${t}`;
    };

    try {
        const response = await fetch(`/api/phase2/update/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                integration: currentData.integration,
                start: combineDT('fd-start', 'fd-start-time'),
                end: combineDT('fd-end', 'fd-end-time'),
                status: getVal('fd-tech-status') || currentData.techStatus,
                technical_details: techDetails
            })
        });
        if (response.ok) {
            window.location.reload();
        } else {
            alert("Error saving details.");
            saveBtn.innerText = "Save Changes";
        }
    } catch (err) {
        console.error(err);
        alert("Network error.");
        saveBtn.innerText = "Save Changes";
    }
}

// ==========================================
// GENERATE RGT DOCUMENT
// ==========================================
async function generateWUD() {
    const id = document.getElementById('fd-id').value;
    const btn = document.getElementById('fd-btn-generate');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = "Generating...";
    btn.disabled = true;
    btn.classList.add('opacity-75');

    try {
        const response = await fetch(`/api/phase2/touchpoint/${id}/generate-wud`);
        if (!response.ok) {
            const e = await response.json();
            alert(e.detail || e.message || "Failed to generate RGT.");
            return;
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const cd = response.headers.get('Content-Disposition');
        a.download = (cd && cd.includes('filename=')) ? cd.split('filename=')[1].replace(/"/g, '') : `RGT_${id}.docx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    } catch (err) {
        console.error(err);
        alert("Network error generating document.");
    } finally {
        btn.innerHTML = originalHTML;
        btn.disabled = false;
        btn.classList.remove('opacity-75');
    }
}

// ==========================================
// WORKSHOP TIMELINE
// ==========================================
function determineWorkshopStage(tp) {
    const techStatus = (tp.techStatus || "").toLowerCase();
    const td = tp.techDetails || {};
    const hasSchedule = tp.start && tp.start !== "-" && tp.start !== "None" && tp.start.trim() !== "";
    const rgtShared = !!td.rgtSharedAt;

    if (techStatus === 'completed') return 5;
    if (techStatus === 'document review') return 4;
    if (techStatus === 'pending document') return 3;
    if (rgtShared) return 2;
    if (hasSchedule) return 1;
    return 0;
}

function updateWorkshopTimeline(stage, tp) {
    const td = tp.techDetails || {};
    const startDate = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start.split(" ")[0] : '';
    const rgtDate = td.rgtSharedAt ? td.rgtSharedAt.split(" ")[0] : '';

    const steps = [
        { dot: 'ws-dot-1', info: 'ws-step1-info', doneText: 'Scheduled' + (startDate ? ' \u00B7 ' + startDate : '') },
        { dot: 'ws-dot-2', info: 'ws-step2-info', doneText: 'Sent' + (rgtDate ? ' \u00B7 ' + rgtDate : '') },
        { dot: 'ws-dot-3', info: 'ws-step3-info', doneText: 'Done \u00B7 Pending Document' },
        { dot: 'ws-dot-4', info: 'ws-step4-info', doneText: 'Document Received' },
        { dot: 'ws-dot-5', info: 'ws-step5-info', doneText: 'Completed' },
    ];

        steps.forEach((step, idx) => {
        const dot = document.getElementById(step.dot);
        const info = document.getElementById(step.info);
        if (!dot || !info) return;

        const stepNum = idx + 1;
        if (stepNum < stage) {
            // Completed step
            dot.className = 'w-3 h-3 rounded-full bg-emerald-500 flex-shrink-0 mt-0.5';
            info.innerText = step.doneText;
            info.className = 'text-[10px] text-emerald-600 mt-0.5 font-medium';
        } else if (stepNum === stage) {
            // Current active step
            dot.className = 'w-3 h-3 rounded-full bg-indigo-500 flex-shrink-0 mt-0.5';
            info.innerText = step.doneText;
            info.className = 'text-[10px] text-indigo-600 mt-0.5 font-medium';
        } else {
            // Future step
            dot.className = 'w-3 h-3 rounded-full bg-slate-300 flex-shrink-0 mt-0.5';
            info.innerText = 'Not started';
            info.className = 'text-[10px] text-slate-400 mt-0.5';
        }
    });
}

// ==========================================
// ATTACHMENTS / DOCUMENTS
// ==========================================
async function loadDocuments(tpId) {
    try {
        const response = await fetch(`/api/phase2/touchpoint/${tpId}/documents`);
        const result = await response.json();
        const container = document.getElementById('fd-documents-list');
        const countBadge = document.getElementById('fd-doc-count');

        if (result.status === 'success' && result.documents.length > 0) {
            countBadge.innerText = `${result.documents.length} file(s)`;
            container.innerHTML = result.documents.map(doc => `
                <div class="flex items-center justify-between p-3 bg-slate-50 border border-slate-100 rounded-lg hover:border-indigo-200 transition-colors">
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 bg-indigo-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <svg class="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                        </div>
                        <div>
                            <p class="text-[12px] font-semibold text-slate-800">${doc.filename}</p>
                            <p class="text-[10px] text-slate-400">${doc.received_at} &middot; ${doc.received_from.split('<')[0].trim()}</p>
                        </div>
                    </div>
                    <a href="/api/phase2/document/${doc.id}/download" class="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-3 py-1.5 rounded-md hover:bg-indigo-100 transition-colors">
                        Download
                    </a>
                </div>
            `).join('');
        } else {
            countBadge.innerText = '0 files';
            container.innerHTML = '<p class="text-sm text-slate-400 italic">No documents received yet.</p>';
        }
    } catch (err) {
        console.error('Failed to load documents:', err);
    }
}