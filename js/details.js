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
    document.getElementById('fd-strip-status').innerText = (tp.techDetails || {}).rgtStatus || 'Pending';

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

    // Workshop Planning Timeline
    const wsStatus = td.workshopStage || determineWorkshopStage(tp);
    updateWorkshopTimeline(wsStatus, tp);

    // Tracking tab
    document.getElementById('fd-discussion').value = td.discussion || "";
    document.getElementById('fd-pointers').value = tp.history_log || "";

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

// Helper: safely set value on an element (won't crash if element removed)
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
    const pointersBox = document.getElementById('fd-pointers');
    pointersBox.dataset.oldLog = pointersBox.value;
    pointersBox.value = "";
    pointersBox.placeholder = "Type a new update to append to the log...";
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
        discussion: document.getElementById('fd-discussion').value,
        pointers: document.getElementById('fd-pointers').value,
        criticality: getVal('fd-criticality'),
        effort: getVal('fd-effort'),
        attendees: getVal('fd-attendees')
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
                status: currentData.techStatus,
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
    // Auto-determine stage based on available data
    const techStatus = (tp.techStatus || "").toLowerCase();
    const hasSchedule = tp.start && tp.start !== "-" && tp.start !== "None";
    const td = tp.techDetails || {};

    if (techStatus === 'completed' || techStatus === 'signed-off') return 3;
    if (hasSchedule || techStatus === 'in progress' || td.apiUrl || td.apiReq) return 2;
    if (tp.owner || tp.source) return 1;
    return 0;
}

function updateWorkshopTimeline(stage, tp) {
    const dot1 = document.getElementById('ws-dot-1');
    const dot2 = document.getElementById('ws-dot-2');
    const dot3 = document.getElementById('ws-dot-3');
    const info1 = document.getElementById('ws-step1-info');
    const info2 = document.getElementById('ws-step2-info');
    const info3 = document.getElementById('ws-step3-info');

    const td = tp.techDetails || {};
    const signoff = tp.signoff || '';
    const startDate = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start.split(" ")[0] : '';

    // Step 1: Scoping
    if (stage >= 1) {
        dot1.className = 'w-3 h-3 rounded-full bg-emerald-500 flex-shrink-0 mt-0.5';
        info1.innerText = 'Done' + (tp.owner ? ' · ' + tp.owner : '');
    } else {
        dot1.className = 'w-3 h-3 rounded-full bg-slate-300 flex-shrink-0 mt-0.5';
        info1.innerText = 'Not started';
    }

    // Step 2: Technical Workshop
    if (stage >= 2) {
        if (stage > 2) {
            dot2.className = 'w-3 h-3 rounded-full bg-emerald-500 flex-shrink-0 mt-0.5';
            info2.innerText = 'Done' + (startDate ? ' · ' + startDate : '');
        } else {
            dot2.className = 'w-3 h-3 rounded-full bg-indigo-500 flex-shrink-0 mt-0.5';
            info2.innerText = (startDate ? 'Scheduled · ' + startDate : 'Pending · Schedule with vendor');
        }
    } else {
        dot2.className = 'w-3 h-3 rounded-full bg-slate-300 flex-shrink-0 mt-0.5';
        info2.innerText = 'Not started';
    }

    // Step 3: Blueprint & Signoff
    if (stage >= 3) {
        dot3.className = 'w-3 h-3 rounded-full bg-emerald-500 flex-shrink-0 mt-0.5';
        info3.innerText = 'Done' + (signoff ? ' · ' + signoff : '');
    } else {
        dot3.className = 'w-3 h-3 rounded-full bg-slate-300 flex-shrink-0 mt-0.5';
        info3.innerText = 'Not started';
    }
}