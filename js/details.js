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
            loadMockInfo(currentData.id);
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

    // Update navigation links with project context
    // (back-arrow, close-icon, phase nav all point to this touchpoint's project)
    if (tp.project_id) {
        const projectUrl = `/project?id=${tp.project_id}`;
        const backLink = document.getElementById('detail-back-link');
        const closeLink = document.getElementById('detail-close-link');
        if (backLink) backLink.href = projectUrl;
        if (closeLink) closeLink.href = projectUrl;
        document.querySelectorAll('.nav-project-link').forEach(a => a.href = projectUrl);
    }

        // Header
    document.getElementById('fd-name').innerText = tp.name;

        // Populate project name pill and breadcrumb links
    const projectName = tp.project_name || "Project";
    const projectId = tp.project_id;
    const projNameEl = document.getElementById('fd-project-name');
    if (projNameEl) {
        projNameEl.innerText = projectName;
    }
    if (projectId) {
        const projectLink = document.getElementById('fd-project-link');
        if (projectLink) projectLink.href = `/project?id=${projectId}`;
        const boardLink = document.getElementById('fd-board-link');
        if (boardLink) boardLink.href = `/project?id=${projectId}`;
    }

    // Key Info Strip
        document.getElementById('fd-strip-module').innerText = tp.module || '-';
    document.getElementById('fd-strip-source').innerText = tp.source || '-';
    document.getElementById('fd-strip-target').innerText = tp.target || '-';
    document.getElementById('fd-strip-integration').innerText = (tp.integration || 'Unassigned').toUpperCase();

        // Basic Info: Profile fields
    document.getElementById('fd-val-flow').innerText = tp.business_flow || '-';

    // Owner fields with department displayed below
    const ownerName = tp.owner || '-';
    const ownerDisplay = tp.owner_display || ownerName;
    document.getElementById('fd-val-owner').innerText = ownerName;
    const ownerDeptEl = document.getElementById('fd-val-owner-dept');
    if (ownerDeptEl) {
        // Extract department from enriched label like "Rahul (CBS)" → "CBS"
        const ownerDeptMatch = ownerDisplay.match(/\(([^)]+)\)/);
        ownerDeptEl.innerText = ownerDeptMatch ? ownerDeptMatch[1] : '';
    }

    const techOwnerName = tp.tech_owner_name || '-';
    const techOwnerDisplay = tp.tech_owner_display || techOwnerName;
    document.getElementById('fd-val-tech-owner').innerText = techOwnerName;
    const techOwnerDeptEl = document.getElementById('fd-val-tech-owner-dept');
    if (techOwnerDeptEl) {
        const techDeptMatch = techOwnerDisplay.match(/\(([^)]+)\)/);
        techOwnerDeptEl.innerText = techDeptMatch ? techDeptMatch[1] : '';
    }

    const modOwnerName = tp.mod_owner || '-';
    const modOwnerDisplay = tp.mod_owner_display || modOwnerName;
    document.getElementById('fd-val-mod-owner').innerText = modOwnerName;
    const modOwnerDeptEl = document.getElementById('fd-val-mod-owner-dept');
    if (modOwnerDeptEl) {
        const modDeptMatch = modOwnerDisplay.match(/\(([^)]+)\)/);
        modOwnerDeptEl.innerText = modDeptMatch ? modDeptMatch[1] : '';
    }

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

    // Workshop Planning Timeline — status synced with the timeline
    const wsStatus = determineWorkshopStage(tp);
    updateWorkshopTimeline(wsStatus, tp);

        // Show/hide Generate WUD and Generate Mock buttons based on Completed status
        const isCompleted = (tp.techStatus || '').toLowerCase() === 'completed';
        const generateBtn = document.getElementById('fd-btn-generate');
        if (generateBtn) {
            if (isCompleted) {
                generateBtn.classList.remove('hidden');
                generateBtn.style.display = 'flex';
            } else {
                generateBtn.classList.add('hidden');
                generateBtn.style.display = '';
            }
        }
        const mockBtn = document.getElementById('fd-btn-generate-mock');
        if (mockBtn) {
            if (isCompleted) {
                mockBtn.classList.remove('hidden');
                mockBtn.style.display = 'flex';
            } else {
                mockBtn.classList.add('hidden');
                mockBtn.style.display = '';
            }
        }

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

    // 6-step flow:
    // 1. Workshop Scheduled
    // 2. RGT Shared
    // 3. In Progress (start_date <= today)
    // 4. Discussion Completed (manual: Pending Document status)
    // 5. Document Review (bank replied with filled RGT)
    // 6. Completed (manual post document review)

    if (techStatus === 'completed') return 6;
    if (techStatus === 'document review') return 5;
    if (techStatus === 'pending document') return 4;
    if (techStatus === 'in progress') return 3;
    if (rgtShared) return 2;
    if (hasSchedule) return 1;
    return 0;
}

function updateWorkshopTimeline(stage, tp) {
    const td = tp.techDetails || {};
    const statusDates = td.statusDates || {};
    const startDate = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start.split(" ")[0] : '';
    const rgtDate = td.rgtSharedAt ? td.rgtSharedAt.split(" ")[0] : '';

    // Build display text with dates for each step
    const scheduledDate = statusDates.scheduled || startDate || '';
    const rgtSharedDate = statusDates.rgtShared || rgtDate || '';
    const inProgressDate = statusDates.inProgress || '';
    const discussionDate = statusDates.discussionCompleted || '';
    const docReviewDate = statusDates.documentReview || '';
    const completedDate = statusDates.completed || '';

    const fmtDate = (label, d) => d ? `${label} \u00B7 ${d}` : label;

    const steps = [
        { dot: 'ws-dot-1', info: 'ws-step1-info', doneText: fmtDate('Scheduled', scheduledDate) },
        { dot: 'ws-dot-2', info: 'ws-step2-info', doneText: fmtDate('RGT Shared', rgtSharedDate) },
        { dot: 'ws-dot-3', info: 'ws-step3-info', doneText: fmtDate('In Progress', inProgressDate) },
        { dot: 'ws-dot-4', info: 'ws-step4-info', doneText: fmtDate('Discussion Completed', discussionDate) },
        { dot: 'ws-dot-5', info: 'ws-step5-info', doneText: fmtDate('Document Received', docReviewDate) },
        { dot: 'ws-dot-6', info: 'ws-step6-info', doneText: fmtDate('Completed', completedDate) },
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

// ==========================================
// GENERATE MOCK: Modal Handlers
// ==========================================

function openGenerateMockModal() {
    const tp = currentData;
    if (!tp) {
        alert("Touchpoint data not loaded.");
        return;
    }

    const td = tp.techDetails || {};

    // Pre-fill method_name from apiName, slugified
    const apiName = (td.apiName || tp.name || "").trim();
    const slug = apiName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
    document.getElementById('mock-method-name').value = slug;

    // Pre-fill HTTP method from apiMethod, default POST
    const httpMethod = (td.apiMethod || "POST").toUpperCase();
    const methodSelect = document.getElementById('mock-http-method');
    if ([...methodSelect.options].some(o => o.value === httpMethod)) {
        methodSelect.value = httpMethod;
    } else {
        methodSelect.value = "POST";
    }

    // Default 200 status code
    document.getElementById('mock-status-code').value = 200;

    // Default JSON content type
    document.getElementById('mock-content-type').value = "application/json";

    // Pre-fill payload from apiRes (success response sample)
    let payload = (td.apiRes || "").trim();
    if (!payload) {
        payload = JSON.stringify({status: "SUCCESS"}, null, 2);
    }
    document.getElementById('mock-payload').value = payload;

        // Clear any stale error
    const errBox = document.getElementById('mock-create-error');
    errBox.classList.add('hidden');
    errBox.textContent = "";

    // Update submit button text based on whether mock exists
    const submitBtn = document.getElementById('mock-create-submit-btn');
    const mockSection = document.getElementById('mock-info-section');
    const hasExisting = mockSection && !mockSection.classList.contains('hidden');
    submitBtn.textContent = hasExisting ? 'Update Mock' : 'Create Mock';

    // Show modal
    document.getElementById('mock-create-modal').classList.remove('hidden');
}

function closeMockCreateModal() {
    document.getElementById('mock-create-modal').classList.add('hidden');
}

async function submitMockCreate() {
    const errBox = document.getElementById('mock-create-error');
    const submitBtn = document.getElementById('mock-create-submit-btn');
    const methodName = document.getElementById('mock-method-name').value.trim();
    const httpMethod = document.getElementById('mock-http-method').value;
    const statusCode = parseInt(document.getElementById('mock-status-code').value, 10);
    const contentType = document.getElementById('mock-content-type').value;
    const payload = document.getElementById('mock-payload').value;

    // Client-side validation
    if (!methodName) {
        errBox.textContent = "Method name is required.";
        errBox.classList.remove('hidden');
        return;
    }
    if (isNaN(statusCode) || statusCode < 100 || statusCode > 599) {
        errBox.textContent = "Status code must be between 100 and 599.";
        errBox.classList.remove('hidden');
        return;
    }
    if (!payload) {
        errBox.textContent = "Payload cannot be empty.";
        errBox.classList.remove('hidden');
        return;
    }

    // Disable submit during request
    submitBtn.disabled = true;
    const originalText = submitBtn.textContent;
    submitBtn.textContent = "Creating...";
    errBox.classList.add('hidden');

    try {
                const resp = await fetch('/api/mocks/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                method_name: methodName,
                http_method: httpMethod,
                status_code: statusCode,
                content_type: contentType,
                payload: payload,
                created_by: "User",
                touchpoint_id: currentData ? currentData.id : null
            })
        });
        const data = await resp.json();

                if (resp.ok) {
                    closeMockCreateModal();
                    showMockSuccess(data.mock_url, httpMethod, data.updated);
                } else {
            errBox.textContent = data.detail || "Failed to create mock.";
            errBox.classList.remove('hidden');
        }
    } catch (err) {
        errBox.textContent = "Network error: " + err.message;
        errBox.classList.remove('hidden');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
    }
}

function showMockSuccess(mockUrl, httpMethod, isUpdate) {
    // mockUrl from API is relative like /mock-api/customer-details
    const absUrl = window.location.origin + mockUrl;
    document.getElementById('mock-success-url').textContent = absUrl;

    const testLink = document.getElementById('mock-success-test-link');
    testLink.href = absUrl;
    testLink.style.display = '';

    // Show method badge (metadata: what the real API expects)
    const methodNote = document.getElementById('mock-success-method');
    if (methodNote) {
        methodNote.textContent = httpMethod + ' ' + mockUrl + ' (actual API method)';
    }

    // Update title based on create vs update
    const titleEl = document.querySelector('#mock-success-modal h3');
    if (titleEl) {
        titleEl.textContent = isUpdate ? 'Mock Updated Successfully' : 'Mock Created Successfully';
    }

    document.getElementById('mock-copy-feedback').textContent = "";
    document.getElementById('mock-success-modal').classList.remove('hidden');
}

async function copyMockUrl() {
    const url = document.getElementById('mock-success-url').textContent;
    try {
        await navigator.clipboard.writeText(url);
        const fb = document.getElementById('mock-copy-feedback');
        fb.textContent = "Copied to clipboard.";
        setTimeout(() => { fb.textContent = ""; }, 2000);
    } catch (err) {
        alert("Could not copy automatically. Please copy manually.");
    }
}

function closeMockSuccessModal() {
    document.getElementById('mock-success-modal').classList.add('hidden');
    // Refresh mock display after creation
    if (currentData) loadMockInfo(currentData.id);
}

// ==========================================
// DEPLOYED MOCK: Load & Display
// ==========================================

async function loadMockInfo(tpId) {
    const container = document.getElementById('mock-info-section');
    if (!container) return;

    try {
        const resp = await fetch(`/api/mocks/by-touchpoint/${tpId}`);
        const data = await resp.json();

        if (data.status === 'success' && data.mock) {
            const m = data.mock;
            const absUrl = window.location.origin + m.mock_url;
            container.innerHTML = `
                <div class="bg-emerald-50 border border-emerald-200 rounded-lg p-3 mt-4">
                    <div class="flex items-center gap-2 mb-2">
                        <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                        <p class="text-[10px] font-bold text-emerald-700 uppercase tracking-wider">Mock Service Live</p>
                    </div>
                    <div class="bg-white border border-emerald-100 rounded-md px-2.5 py-1.5 mb-2">
                        <p class="text-[11px] font-mono text-slate-700 break-all">${absUrl}</p>
                    </div>
                    <div class="flex items-center gap-3 text-[10px] text-slate-500">
                        <span class="font-bold text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">${m.http_method}</span>
                        <span>Status: ${m.status_code}</span>
                        <span>${m.content_type}</span>
                    </div>
                    <div class="flex items-center gap-2 mt-2">
                        <a href="${absUrl}" target="_blank" rel="noopener" class="text-[10px] font-bold text-emerald-700 hover:text-emerald-900 underline">Test</a>
                        <button onclick="copyToClipboard('${absUrl}')" class="text-[10px] font-bold text-slate-500 hover:text-slate-700 underline">Copy URL</button>
                    </div>
                </div>
            `;
            container.classList.remove('hidden');

            // Update the Generate Mock button text to "Update Mock"
            const mockBtn = document.getElementById('fd-btn-generate-mock');
            if (mockBtn) {
                mockBtn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 100-4h14a2 2 0 100 4M5 12a2 2 0 110 4h14a2 2 0 110-4"></path></svg> Update Mock`;
            }
        } else {
            container.innerHTML = '';
            container.classList.add('hidden');

            // Reset button text to "Generate Mock"
            const mockBtn = document.getElementById('fd-btn-generate-mock');
            if (mockBtn) {
                mockBtn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 100-4h14a2 2 0 100 4M5 12a2 2 0 110 4h14a2 2 0 110-4"></path></svg> Generate Mock`;
            }
        }
    } catch (err) {
        console.error('Failed to load mock info:', err);
    }
}

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        alert('Copied!');
    } catch (err) {
        alert('Could not copy. Please copy manually: ' + text);
    }
}