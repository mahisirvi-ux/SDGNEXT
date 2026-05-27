let currentData = null;
let edsOutputFields = [];

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
                  
        // NEW CODE: Configurator Button Logic
        const isApi = (tp.integration || '').toLowerCase() === 'api';
        const isDocReview =['document review', 'completed'].includes((tp.techStatus || '').toLowerCase());
        const configBtn = document.getElementById('fd-btn-configurator');
        
        if (configBtn) {
            if (isApi && isDocReview) {
                configBtn.classList.remove('hidden');
                configBtn.style.display = 'flex';
            } else {
                configBtn.classList.add('hidden');
                configBtn.style.display = '';
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
        const result = await response.json();
        if (response.ok && result.status === 'success') {
            window.location.reload();
        } else {
            alert("Error saving: " + (result.message || "Unknown error"));
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
// ==========================================
// CONFIGURATOR & EDS HELPERS
// ==========================================

// ⚠️ CRITICAL: The sleep function that powers the animation timing
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ==========================================
// ROBUST TYPEWRITER ENGINE
// ==========================================
async function typeText(element, text, makeReadonlyAfter = true, speed = 35) {
    if (!element) return;
    
    // Force string conversion so empty values don't break the animation
    const safeText = String(text || ''); 

    // Add glow and scale effect
    element.classList.add('typing-highlight');
    element.value = '';

    // Type characters
    for (let i = 0; i < safeText.length; i++) {
        element.value += safeText.charAt(i);
        await sleep(speed);
    }

    // Remove glow, apply final styled state
    element.classList.remove('typing-highlight');
    if (makeReadonlyAfter) {
        element.readOnly = true;
        element.classList.add('border-indigo-300', 'bg-indigo-50', 'text-indigo-900', 'font-mono');
    }
}

// ==========================================
// STEP 1: CONFIGURATOR MENU & CONNECTION
// ==========================================
function openConfiguratorModal() {
    document.getElementById('config-menu-modal').classList.remove('hidden');
}

function closeConfigMenuModal() {
    document.getElementById('config-menu-modal').classList.add('hidden');
}

function closeConfiguratorModal() {
    document.getElementById('configurator-modal').classList.add('hidden');
}

async function startConnectionAnimation() {
    if (!currentData) return;
    const tp = currentData;
    const td = tp.techDetails || {};

    closeConfigMenuModal();
    document.getElementById('configurator-modal').classList.remove('hidden');

    const targetName = tp.name || '';
    let targetBaseUrl = (td.uatUrl || '').trim();
    let endpoint = (td.endpointUrl || '').trim();
    if (targetBaseUrl && endpoint && targetBaseUrl.endsWith(endpoint)) {
        targetBaseUrl = targetBaseUrl.slice(0, -endpoint.length);
    }
    if (targetBaseUrl.endsWith('/')) targetBaseUrl = targetBaseUrl.slice(0, -1);

    const headersStr = td.mandatoryHeaders || '';
    const headersList = headersStr.split(',').map(h => h.trim()).filter(h => h.length > 0);

    const nameField = document.getElementById('config-name');
    const urlField = document.getElementById('config-base-url');
    nameField.value = '';
    urlField.value = '';
    
    const headersContainer = document.getElementById('config-headers-container');
    headersContainer.innerHTML = '';
    const headerFieldsToType = [];

    if (headersList.length > 0) {
        headersList.forEach((headerStr, index) => {
            let key = headerStr;
            let value = '';
            if (headerStr.includes(':')) {
                const parts = headerStr.split(':');
                key = parts[0].trim();
                value = parts.slice(1).join(':').trim();
            } else if (headerStr.includes('=')) {
                const parts = headerStr.split('=');
                key = parts[0].trim();
                value = parts.slice(1).join('=').trim();
            }
            
            const keyId = `config-hdr-key-${index}`;
            const valId = `config-hdr-val-${index}`;
            appendEmptyConfigHeaderRow(keyId, valId);
            
            headerFieldsToType.push({ el: document.getElementById(keyId), text: key, isReadonly: true });
            if (value) headerFieldsToType.push({ el: document.getElementById(valId), text: value, isReadonly: false });
        });
    } else {
        appendEmptyConfigHeaderRow('config-hdr-key-0', 'config-hdr-val-0');
    }

    await sleep(600);
    await typeText(nameField, targetName);
    await sleep(400);
    await typeText(urlField, targetBaseUrl);
    await sleep(400);
    
    for (const field of headerFieldsToType) {
        await typeText(field.el, field.text, field.isReadonly);
        await sleep(300);
    }
}

function appendEmptyConfigHeaderRow(keyId, valId) {
    const container = document.getElementById('config-headers-container');
    const row = document.createElement('div');
    row.className = 'grid grid-cols-2 gap-4 items-center';
    row.innerHTML = `
        <input type="text" id="${keyId}" class="w-full text-sm border border-slate-200 rounded-md px-3 py-2 transition-all" placeholder="Key">
        <input type="text" id="${valId}" class="w-full text-sm border border-slate-200 rounded-md px-3 py-2 transition-all" placeholder="Value">
    `;
    container.appendChild(row);
}

// ==========================================
// STEP 2: EDS CONFIGURATION (AI BACKEND CONNECTED)
// ==========================================
let currentEdsTab = 1;

async function startEdsAnimation() {
    if (!currentData) return;
    const tp = currentData;
    const td = tp.techDetails || {};

    // Hide Menu, Show EDS Modal
    closeConfigMenuModal();
    document.getElementById('eds-config-modal').classList.remove('hidden');
    edsShowTab(1); 

    document.getElementById('eds-status-text').innerText = "Mapping General Information...";

    // --- PAGE 1 MAPPINGS ---
    const outTypeStr = (td.apiRes || '').trim().startsWith('<') ? 'XML' : 'JSON';
    
    await sleep(400);
    await typeText(document.getElementById('eds-name'), tp.name);
    await typeText(document.getElementById('eds-method-name'), td.endpointUrl);
    await typeText(document.getElementById('eds-desc'), tp.business_flow);
    await typeText(document.getElementById('eds-method-type'), td.apiMethod || 'POST');
    await typeText(document.getElementById('eds-output-type'), outTypeStr);

    // --- PREPARE PAGE 2 (Template via AI Backend) ---
    document.getElementById('eds-status-text').innerText = "AI Agent generating Request Template...";
    const reqStr = (td.apiReq || '').trim();
    const inputTypeStr = reqStr.startsWith('<') ? 'XML' : (reqStr.startsWith('{') ? 'JSON' : 'QUERYSTRING');
    
    await typeText(document.getElementById('eds-input-type'), inputTypeStr);

    let templateStr = "";
    if (reqStr) {
        try {
            const tResp = await fetch('/api/integrations/eds/generate-template', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ payload: reqStr })
            });
            const tData = await tResp.json();
            templateStr = tData.template;
        } catch(e) {
            console.error("Template Gen Error:", e);
            templateStr = "Error contacting AI Agent.";
        }
    } else {
        templateStr = "{\n  \"message\": \"No request sample provided in touchpoint\"\n}";
    }
    document.getElementById('eds-template').value = templateStr;

    // --- PREPARE PAGE 3 (XSLT & Grid via AI Backend) ---
    document.getElementById('eds-status-text').innerText = "AI Agent writing XSLT Transformation Logic...";
    const resStr = (td.apiRes || '').trim();
    const errStr = (td.errorSample || '').trim();
    
    let xsltStr = "";
    let combinedKeys = [];
    
    if (resStr || errStr) {
        try {
            const xResp = await fetch('/api/integrations/eds/generate-xslt', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    success_payload: resStr, 
                    error_payload: errStr 
                })
            });
            const xData = await xResp.json();
            xsltStr = xData.xslt || "Error generating XSLT.";
            combinedKeys = xData.parameters || [];
        } catch(e) {
            console.error("XSLT Gen Error:", e);
            xsltStr = "Error contacting AI Agent.";
        }
    } else {
        xsltStr = "";
    }
    
        document.getElementById('eds-xslt').value = xsltStr;

    // Store output fields at module level for finishEdsConfiguration
    edsOutputFields = combinedKeys;

    // Build Output Grid
    const gridContainer = document.getElementById('eds-output-grid');
    if (combinedKeys && combinedKeys.length > 0) {
        gridContainer.innerHTML = combinedKeys.map(key => `
            <div class="grid grid-cols-2 gap-2 p-1 border-b border-slate-100 last:border-0">
                <span class="font-mono text-[10px] font-bold text-slate-700">${key}</span>
                <span class="text-[10px] text-slate-500">STRING</span>
            </div>
        `).join('');
    } else {
        gridContainer.innerHTML = '<p class="text-xs text-slate-400 italic p-2">No output parameters detected.</p>';
    }

    document.getElementById('eds-status-text').innerText = "Configuration Ready. Review steps.";
}

// ==========================================
// EDS TAB NAVIGATION
// ==========================================
function edsShowTab(tabNum) {
    currentEdsTab = tabNum;
    
    document.querySelectorAll('.eds-page').forEach(p => p.classList.add('hidden'));
    document.getElementById(`eds-page-${tabNum}`).classList.remove('hidden');
    
    document.querySelectorAll('.eds-tab-btn').forEach((btn, idx) => {
        if (idx + 1 === tabNum) {
            btn.classList.replace('text-slate-500', 'text-[#006b8f]');
            btn.classList.replace('border-transparent', 'border-[#006b8f]');
        } else {
            btn.classList.replace('text-[#006b8f]', 'text-slate-500');
            btn.classList.replace('border-[#006b8f]', 'border-transparent');
        }
    });

    document.getElementById('eds-prev-btn').classList.toggle('hidden', tabNum === 1);
    const nextBtn = document.getElementById('eds-next-btn');
        if (tabNum === 3) {
        nextBtn.innerText = "Finish Configuration";
        nextBtn.onclick = () => finishEdsConfiguration();
    } else {
        nextBtn.innerText = "Next Step";
        nextBtn.onclick = () => edsSwitchTab(1);
    }
}

function edsSwitchTab(direction) {
    let newTab = currentEdsTab + direction;
    if (newTab >= 1 && newTab <= 3) {
        edsShowTab(newTab);
    }
}
// ================================================
// API's Connection — Save button handler
// Inserts MASHUPCONNECTION then MASHUPWSCONNECTION
// in one sequential operation. Idempotent.
// ================================================
async function saveApiConnection() {
    const tp = currentData;
    if (!tp) {
        alert("Touchpoint data not loaded.");
        return;
    }

    const saveBtn = document.getElementById('config-save-btn');
    const statusDiv = document.getElementById('config-save-status');

    // Disable immediately to prevent duplicate concurrent requests
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    statusDiv.className = "text-xs font-medium px-4 py-2 " +
        "rounded-md w-full text-center max-w-md " +
        "bg-blue-50 text-blue-700";
    statusDiv.textContent = "Step 1/2: Creating MASHUPCONNECTION...";
    statusDiv.classList.remove('hidden');

    try {
        // Step 1: MASHUPCONNECTION
        const connResp = await fetch(
            `/api/crm/mashup/insert/${tp.id}`,
            { method: "POST",
              headers: { "Content-Type": "application/json" } }
        );
        const connData = await connResp.json();

        if (!connResp.ok || !connData.success) {
            throw new Error(
                connData.detail || connData.message ||
                "MASHUPCONNECTION insert failed."
            );
        }

        const connAction = connData.is_update
            ? "updated" : "created";
        const connectionId = connData.connection_id;

        // Step 2: MASHUPWSCONNECTION
        statusDiv.textContent =
            "Step 2/2: Creating MASHUPWSCONNECTION...";

        const wsResp = await fetch(
            `/api/crm/mashupws/insert/${tp.id}`,
            { method: "POST",
              headers: { "Content-Type": "application/json" } }
        );
        const wsData = await wsResp.json();

        if (!wsResp.ok || !wsData.success) {
            throw new Error(
                wsData.detail || wsData.message ||
                "MASHUPWSCONNECTION insert failed."
            );
        }

        const wsAction = wsData.is_update
            ? "updated" : "created";

        // Success state
        statusDiv.className = "text-xs font-medium px-4 py-2 " +
            "rounded-md w-full text-center max-w-md " +
            "bg-emerald-50 text-emerald-700 border " +
            "border-emerald-200";
        statusDiv.textContent =
            `\u2713 Connection ${connAction} (ID: ${connectionId}) ` +
            `and WS connection ${wsAction} successfully.`;
        saveBtn.textContent = "Saved \u2713";

        // Auto-close after 2 seconds
        setTimeout(() => {
            closeConfiguratorModal();
            saveBtn.disabled = false;
            saveBtn.textContent = "Save";
            statusDiv.classList.add('hidden');
        }, 2000);

    } catch (err) {
        // Error state — keep modal open so user can fix and retry
        statusDiv.className = "text-xs font-medium px-4 py-2 " +
            "rounded-md w-full text-center max-w-md " +
            "bg-red-50 text-red-700 border border-red-200";
                statusDiv.textContent = "\u2717 " + err.message;
        saveBtn.disabled = false;
        saveBtn.textContent = "Save";
    }
}

// ================================================
// EDS Configuration — Finish button handler
// Inserts MASHUPDATASOURCE into Oracle.
// Idempotent: one touchpoint = one datasource row.
// ================================================
async function finishEdsConfiguration() {
    const tp = currentData;
    if (!tp) {
        alert("Touchpoint data not loaded.");
        return;
    }

    // Validate: XSLT must be generated
    const xslt = (document.getElementById('eds-xslt').value || "").trim();
    if (!xslt) {
        alert("XSLT has not been generated yet. Wait for the AI Agent to complete.");
        return;
    }

    const nextBtn = document.getElementById('eds-next-btn');
    const statusText = document.getElementById('eds-status-text');

    // Disable immediately to prevent duplicate requests
    nextBtn.disabled = true;
    nextBtn.innerText = "Saving...";
    statusText.innerText = "Inserting MASHUPDATASOURCE...";
    statusText.className = "text-xs text-blue-600 font-bold italic";

    // Gather form values
    const name = (document.getElementById('eds-name').value || "").trim();
    const source = (document.getElementById('eds-method-name').value || "").trim();
    const dataXpath = (document.getElementById('eds-xpath').value || "response").trim();

    try {
        const resp = await fetch(
            `/api/crm/datasource/insert/${tp.id}`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                    name: name,
                    source: source,
                    xslt: xslt,
                    data_xpath: dataXpath,
                    output_fields: edsOutputFields
                })
            }
        );
        const data = await resp.json();

        if (!resp.ok || !data.success) {
            throw new Error(
                data.detail || data.message ||
                "MASHUPDATASOURCE insert failed."
            );
        }

        const action = data.is_update ? "updated" : "created";

                // Success state
        const fieldsCount = data.fields_created || 0;
        statusText.className = "text-xs text-emerald-600 font-bold italic";
        statusText.innerText =
            `\u2713 Datasource ${action} (ID: ${data.datasource_id}), ` +
            `${fieldsCount} fields mapped`;
        nextBtn.innerText = "Done \u2713";

        // Auto-close after 2 seconds
        setTimeout(() => {
            document.getElementById('eds-config-modal').classList.add('hidden');
            nextBtn.disabled = false;
            nextBtn.innerText = "Finish Configuration";
            statusText.innerText = "Configuration Ready. Review steps.";
            statusText.className = "text-xs text-indigo-600 font-bold italic";
        }, 2000);

    } catch (err) {
        // Error state — keep modal open for retry
        statusText.className = "text-xs text-red-600 font-bold italic";
        statusText.innerText = "\u2717 " + err.message;
        nextBtn.disabled = false;
        nextBtn.innerText = "Finish Configuration";
    }
}