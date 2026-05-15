// ==========================================
// GLOBAL STATE MANAGEMENT
// ==========================================
window.phase2DataMap = {}; 
window.currentEditingTechId = null;

// ==========================================
// MASTER NAVIGATION LOGIC (Sidebar)
// ==========================================
/*function switchPhase(phaseNumber) {
    document.getElementById('phase1-board').classList.add('hidden');
    document.getElementById('phase1-board').classList.remove('block');
    document.getElementById('phase2-board').classList.add('hidden');
    document.getElementById('phase2-board').classList.remove('block');
    document.getElementById('phase3-board').classList.add('hidden');
    document.getElementById('phase3-board').classList.remove('flex');

    const navs = [document.getElementById('nav-1'), document.getElementById('nav-2'), document.getElementById('nav-3')];
    navs.forEach(nav => {
        if(nav) {
            nav.classList.remove('bg-pink-500', 'text-white');
            nav.classList.add('text-slate-400', 'hover:text-white', 'hover:bg-slate-700');
        }
    });

    if (phaseNumber === 1) {
        document.getElementById('phase1-board').classList.remove('hidden');
        document.getElementById('phase1-board').classList.add('block');
        document.getElementById('nav-1').classList.remove('text-slate-400', 'hover:text-white', 'hover:bg-slate-700');
        document.getElementById('nav-1').classList.add('bg-pink-500', 'text-white');
    } 
    else if (phaseNumber === 2) {
        document.getElementById('phase2-board').classList.remove('hidden');
        document.getElementById('phase2-board').classList.add('block');
        document.getElementById('nav-2').classList.remove('text-slate-400', 'hover:text-white', 'hover:bg-slate-700');
        document.getElementById('nav-2').classList.add('bg-pink-500', 'text-white');

        // Ensure detail view is hidden and table is showing when navigating
        document.getElementById('tech-detail-view').classList.add('hidden');
        document.getElementById('tech-detail-view').classList.remove('block');
        document.getElementById('tech-dashboard-view').classList.remove('hidden');
        document.getElementById('tech-dashboard-view').classList.add('block');

        // --- CLEAR STALE DATA FROM PREVIOUS PROJECT ---
        // Wipe the cached map and visible rows so no other project's data leaks through
        window.phase2DataMap = {};
        const tbody = document.getElementById('tech-table-body');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-5 py-12 text-center text-sm font-medium text-slate-400">Loading project data...</td></tr>';
        }
        // Reset KPI counters to zero while loading
        ['tech-metric-total','tech-metric-pending','tech-metric-scheduled',
         'tech-metric-rescheduled','tech-metric-inprogress','tech-metric-delayed'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerText = '0';
        });

        // Sync current project from the selector (single source of truth)
        const selector = document.getElementById('projectSelector');
        if (selector && selector.value) {
            window.currentProjectName = selector.value;
        }

        populateTechTable();
    }
    else if (phaseNumber === 3) {
        document.getElementById('phase3-board').classList.remove('hidden');
        document.getElementById('phase3-board').classList.add('flex');
        document.getElementById('nav-3').classList.remove('text-slate-400', 'hover:text-white', 'hover:bg-slate-700');
        document.getElementById('nav-3').classList.add('bg-pink-500', 'text-white');
    }
} */

// ==========================================
// PHASE 2: REAL DATA FETCHING & RENDERING
// ==========================================
async function populateTechTable() {
    const tbody = document.getElementById('tech-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="7" class="px-5 py-12 text-center text-sm font-medium text-slate-400">Loading data...</td></tr>';
    try {
        // Read the current project from the global state (set by Phase 1's project selector)
        // Read the current project from global state (set by app-dashboard.js on project switch)
        const currentProject = window.currentProjectName || document.getElementById('projectSelector')?.value || '';
        const response = await fetch(`/api/phase2/dashboard?project=${encodeURIComponent(currentProject)}&t=${new Date().getTime()}`);
        const result = await response.json();
        const eligibleItems = result.data || [];

        let countPending = 0;
        let countScheduled = 0;
        let countRescheduled = 0; // <--- NEW: Initialize Counter
        let countInProgress = 0;
        let countDelayed = 0;
        // ---------------------------------

        if (eligibleItems.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="px-5 py-12 text-center text-sm text-slate-500 italic">No touchpoints have been signed off in Phase 1 yet.</td></tr>`;
            
            // Zero out metrics if empty
            document.getElementById('tech-metric-total').innerText = 0;
            document.getElementById('tech-metric-pending').innerText = 0;
            document.getElementById('tech-metric-scheduled').innerText = 0;
            document.getElementById('tech-metric-rescheduled').innerText = 0; // <--- NEW: Zero out
            document.getElementById('tech-metric-inprogress').innerText = 0;
            document.getElementById('tech-metric-delayed').innerText = 0;
            return;
        }

        tbody.innerHTML = ''; 
        window.phase2DataMap = {}; 

        let visibleCount = 0;
        const filterFn = (typeof window.matchesPhase2Filters === 'function')
            ? window.matchesPhase2Filters
            : () => true;

        eligibleItems.forEach(tp => {
            window.phase2DataMap[tp.id] = tp; 

            // --- COUNT THE CORRECT STATUSES (always, even for filtered-out rows) ---
            if (tp.techStatus === 'Pending Workshop') countPending++;
            if (tp.techStatus === 'Scheduled') countScheduled++;
            if (tp.techStatus === 'Rescheduled') countRescheduled++; // <--- NEW: Count the status
            if (tp.techStatus === 'In Progress') countInProgress++;
            if (tp.techStatus === 'Delayed') countDelayed++;

            // --- FILTER GATE: skip rendering this row if it doesn't match active filters ---
            if (!filterFn(tp)) return;
            visibleCount++;

            const tr = document.createElement('tr');
            tr.className = "hover:bg-slate-50 transition-colors border-b border-slate-100";

            // Backend now sends "YYYY-MM-DD HH:MM". Split into [date, time] so we can
            // render the two inputs side by side. Empty string -> both blank.
            const rawStart = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start : "";
            const rawEnd   = (tp.end   && tp.end   !== "-" && tp.end   !== "None") ? tp.end   : "";
            const [startDate = "", startTime = ""] = rawStart.split(" ");
            const [endDate   = "", endTime   = ""] = rawEnd.split(" ");
            
            const rawOwner = tp.owner || "Unassigned";
            const ownerOnly = typeof rawOwner === 'string' && rawOwner.includes('(') 
                ? rawOwner.split(' (')[0].trim() 
                : rawOwner;

            // --- THESE ARE THE TWO LINES THAT WENT MISSING! ---
           // --- NEW: Safe Integration Logic ---
                        const safeIntegration = tp.integration || 'unassigned';
            const integrationDisplay = safeIntegration === 'unassigned' 
                ? '<span class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium text-amber-600 bg-amber-50 border border-amber-200 rounded-md">Pending</span>' 
                : `<span class="inline-flex items-center px-2 py-0.5 text-[10px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-md uppercase">${safeIntegration}</span>`;

            // Setup the selected state for the new Integration Dropdown
            const isApi = safeIntegration.toLowerCase() === 'api' ? 'selected' : '';
            const isDb = safeIntegration.toLowerCase() === 'database' ? 'selected' : '';
            const isUnassignedInteg = (!isApi && !isDb) ? 'selected' : '';
            // ------------------------------------

            const isCompleted = tp.techStatus === 'Completed' ? 'selected' : '';
            const isRescheduled = tp.techStatus === 'Rescheduled' ? 'selected' : '';
            const isAuto = (!isCompleted && !isRescheduled) ? 'selected' : '';

                        tr.innerHTML = `
                            <td class="px-5 py-3.5">
                                <a href="/details?id=${tp.id}" class="text-sm font-semibold text-[#1a233a] hover:text-indigo-600 transition-colors leading-snug block">${tp.name}</a>
                                <span class="text-[10px] text-slate-400 font-medium">${tp.source_system && tp.source_system !== '-' ? tp.source_system : ''}</span>
                            </td>
                
                            <td class="px-4 py-3.5">
                                <span class="text-xs text-slate-600 font-medium">${tp.module}</span>
                            </td>

                            <td class="px-4 py-3.5">
                                <div id="integ-view-${tp.id}">
                                    ${integrationDisplay}
                                </div>
                                <select id="integ-edit-${tp.id}" class="hidden text-xs border border-slate-300 rounded-md px-2 py-1 shadow-sm bg-white w-full max-w-[110px] focus:ring-2 focus:ring-indigo-500">
                                    <option value="unassigned" ${isUnassignedInteg}>Unassigned</option>
                                    <option value="api" ${isApi}>API</option>
                                    <option value="database" ${isDb}>Database</option>
                                </select>
                            </td>
                
                            <td class="px-4 py-3.5">
                                <span class="text-xs text-slate-700 font-medium">${ownerOnly}</span>
                            </td>
                
                            <td class="px-4 py-3.5">
                                <div class="space-y-1">
                                    <div class="flex items-center gap-1.5">
                                        <span class="text-[9px] font-bold text-emerald-500 w-3">S</span>
                                        <input type="datetime-local" id="start-dt-${tp.id}" value="${rawStart ? rawStart.replace(' ', 'T') : ''}" class="text-[11px] border border-slate-200 rounded-md px-1.5 py-0.5 bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed w-[155px] focus:ring-1 focus:ring-indigo-400" disabled>
                                    </div>
                                    <div class="flex items-center gap-1.5">
                                        <span class="text-[9px] font-bold text-red-400 w-3">E</span>
                                        <input type="datetime-local" id="end-dt-${tp.id}" value="${rawEnd ? rawEnd.replace(' ', 'T') : ''}" class="text-[11px] border border-slate-200 rounded-md px-1.5 py-0.5 bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed w-[155px] focus:ring-1 focus:ring-indigo-400" disabled>
                                    </div>
                                </div>
                            </td>
                
                            <td class="px-4 py-3.5">
                                <span id="status-pill-${tp.id}" class="inline-flex px-2.5 py-1 text-[10px] uppercase font-bold rounded-md border ${tp.statusClass} whitespace-nowrap">${tp.techStatus}</span>
                                <select id="status-edit-${tp.id}" class="hidden text-xs border border-slate-300 rounded-md px-2 py-1 shadow-sm bg-white w-full max-w-[115px] focus:ring-2 focus:ring-indigo-500">
                                    <option value="Auto" ${isAuto}>Auto-Calculate</option>
                                    <option value="Completed" ${isCompleted}>Completed</option>
                                    <option value="Rescheduled" ${isRescheduled}>Rescheduled</option>
                                </select>
                            </td>
                
                            <td class="px-4 py-3.5 text-center">
                                <button id="edit-btn-${tp.id}" onclick="enableEditMode(${tp.id})" class="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-indigo-600 bg-slate-50 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 rounded-md px-2.5 py-1.5 transition-all">
                                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg>
                                    Edit
                                </button>
                                <button id="save-btn-${tp.id}" onclick="saveRowChanges(${tp.id})" class="hidden inline-flex items-center gap-1 bg-emerald-500 hover:bg-emerald-600 text-white text-[10px] uppercase font-bold py-1.5 px-3 rounded-md shadow-sm transition-all">
                                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                                    Save
                                </button>
                            </td>
                        `;
            tbody.appendChild(tr);
        });
        document.getElementById('tech-metric-total').innerText = eligibleItems.length;
        document.getElementById('tech-metric-pending').innerText = countPending;
        document.getElementById('tech-metric-scheduled').innerText = countScheduled;
        document.getElementById('tech-metric-rescheduled').innerText = countRescheduled; // <--- NEW: Push to UI
        document.getElementById('tech-metric-inprogress').innerText = countInProgress;
        document.getElementById('tech-metric-delayed').innerText = countDelayed;

        // Update the module filter dropdown with available modules
        updatePhase2ModuleFilter();

        // If active filters hid every row, show a friendly empty state
                if (visibleCount === 0 && eligibleItems.length > 0) {
                    tbody.innerHTML = `<tr><td colspan="7" class="px-5 py-12 text-center text-sm text-slate-500 italic">No touchpoints match the active filters. <button onclick="clearPhase2Filters()" class="text-pink-500 font-bold underline ml-1">Clear filters</button></td></tr>`;
        }
    } catch (error) {
        console.error("Error fetching live Phase 2 data:", error);
        tbody.innerHTML = `<tr><td colspan="9" class="px-5 py-8 text-center text-sm font-bold text-red-500">Failed to load data.</td></tr>`;
    }
}

// ==========================================
// INLINE EDITING LOGIC (Control Tower)
// ==========================================
function enableEditMode(touchpointId) {
    const ids = [
        `start-dt-${touchpointId}`,
        `end-dt-${touchpointId}`
    ];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.disabled = false;
            el.classList.replace('bg-slate-50', 'bg-white');
        }
    });

    // --- NEW: Toggle Integration Dropdown ---
    document.getElementById(`integ-view-${touchpointId}`).classList.add('hidden');
    document.getElementById(`integ-edit-${touchpointId}`).classList.remove('hidden');
    // ----------------------------------------

    // Toggle the Status View to Edit Dropdown
    document.getElementById(`status-pill-${touchpointId}`).classList.add('hidden');
    document.getElementById(`status-edit-${touchpointId}`).classList.remove('hidden');

    document.getElementById(`edit-btn-${touchpointId}`).classList.add('hidden');
    document.getElementById(`save-btn-${touchpointId}`).classList.remove('hidden');
}

async function saveRowChanges(touchpointId) {
    const saveBtn = document.getElementById(`save-btn-${touchpointId}`);
    saveBtn.innerText = "Saving...";
    saveBtn.classList.add("opacity-50", "cursor-not-allowed");

        // Read datetime-local values and convert to "YYYY-MM-DD HH:MM" format
    const formatDt = (id) => {
        const val = (document.getElementById(id)?.value || "").trim();
        if (!val) return "";
        return val.replace("T", " ");
    };

    const payload = {
        integration: document.getElementById(`integ-edit-${touchpointId}`).value,
        start: formatDt(`start-dt-${touchpointId}`),
        end:   formatDt(`end-dt-${touchpointId}`),
        // Harvest the manual status override
        status: document.getElementById(`status-edit-${touchpointId}`).value
    };

    try {
        const response = await fetch(`/api/phase2/update/${touchpointId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const resData = await response.json();
        
        if (response.ok && resData.status === "success") {
            populateTechTable(); 
        } else {
            alert("Backend Error: " + resData.message);
            saveBtn.innerText = "Save";
            saveBtn.classList.remove("opacity-50", "cursor-not-allowed");
        }
    } catch (err) {
        console.error("Save failed:", err);
        alert("Network error.");
        saveBtn.innerText = "Save";
        saveBtn.classList.remove("opacity-50", "cursor-not-allowed");
    }
}

// ==========================================
// PHASE 2: DETAIL FORM (TECHNICAL BLUEPRINT)
// ==========================================
function openTechDetail(touchpointId) {
    const tp = window.phase2DataMap[touchpointId];
    window.currentEditingTechId = touchpointId;

    document.getElementById('tech-dashboard-view').classList.add('hidden');
    document.getElementById('tech-dashboard-view').classList.remove('block');
    document.getElementById('tech-detail-view').classList.remove('hidden');
    document.getElementById('tech-detail-view').classList.add('block');

    document.getElementById('tech-detail-title').innerText = tp.name;
    document.getElementById('tech-detail-module').innerText = "Module: " + tp.module;
    document.getElementById('tech-integration-type').value = tp.integration || 'unassigned';
    
    // Pass the saved JSON data into the render function to pre-fill inputs
    renderTechFields(tp.techDetails || {});
}

function closeTechDetail() {
    document.getElementById('tech-detail-view').classList.add('hidden');
    document.getElementById('tech-detail-view').classList.remove('block');
    document.getElementById('tech-dashboard-view').classList.remove('hidden');
    document.getElementById('tech-dashboard-view').classList.add('block');
    
    populateTechTable(); 
}

function renderTechFields(existingData = {}) {
    const integrationType = document.getElementById('tech-integration-type').value;
    const container = document.getElementById('dynamic-tech-fields');
    
    container.innerHTML = '';
    const inputClasses = "w-full text-sm border border-slate-300 rounded-md p-2.5 bg-white focus:ring-2 focus:ring-pink-500 focus:border-pink-500 shadow-sm mb-4";
    const labelClasses = "block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 mt-4";

    if (integrationType === 'api') {
        container.innerHTML = `
            <h4 class="text-sm font-bold text-[#1a233a] border-b border-slate-200 pb-2 mb-4">API Configuration</h4>
            <label class="${labelClasses}">Endpoint URL:</label>
            <input type="text" id="api-url" value="${existingData.url || ''}" placeholder="https://api.vendor.com/v1/data" class="${inputClasses}">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="${labelClasses}">HTTP Method:</label>
                    <select id="api-method" class="${inputClasses}">
                        <option value="POST" ${existingData.method === 'POST' ? 'selected' : ''}>POST</option>
                        <option value="GET" ${existingData.method === 'GET' ? 'selected' : ''}>GET</option>
                        <option value="PUT" ${existingData.method === 'PUT' ? 'selected' : ''}>PUT</option>
                    </select>
                </div>
                <div>
                    <label class="${labelClasses}">Authentication Type:</label>
                    <select id="api-auth" class="${inputClasses}">
                        <option value="OAuth 2.0" ${existingData.auth === 'OAuth 2.0' ? 'selected' : ''}>OAuth 2.0</option>
                        <option value="API Key" ${existingData.auth === 'API Key' ? 'selected' : ''}>API Key</option>
                        <option value="Basic Auth" ${existingData.auth === 'Basic Auth' ? 'selected' : ''}>Basic Auth</option>
                    </select>
                </div>
            </div>
        `;
    } 
    else if (integrationType === 'database') {
        container.innerHTML = `
            <h4 class="text-sm font-bold text-[#1a233a] border-b border-slate-200 pb-2 mb-4">Database Configuration</h4>
            <label class="${labelClasses}">Target Schema/Database:</label>
            <input type="text" id="db-schema" value="${existingData.schema || ''}" placeholder="e.g., CRM_PROD" class="${inputClasses}">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="${labelClasses}">DB Engine:</label>
                    <select id="db-engine" class="${inputClasses}">
                        <option value="Oracle" ${existingData.engine === 'Oracle' ? 'selected' : ''}>Oracle</option>
                        <option value="PostgreSQL" ${existingData.engine === 'PostgreSQL' ? 'selected' : ''}>PostgreSQL</option>
                        <option value="SQL Server" ${existingData.engine === 'SQL Server' ? 'selected' : ''}>SQL Server</option>
                    </select>
                </div>
                <div>
                    <label class="${labelClasses}">Object Type:</label>
                    <select id="db-object" class="${inputClasses}">
                        <option value="Table" ${existingData.object === 'Table' ? 'selected' : ''}>Table (Direct Insert)</option>
                        <option value="View" ${existingData.object === 'View' ? 'selected' : ''}>View (Read Only)</option>
                        <option value="Stored Procedure" ${existingData.object === 'Stored Procedure' ? 'selected' : ''}>Stored Procedure</option>
                    </select>
                </div>
            </div>
        `;
    }
    else if (integrationType === 'batch') {
        container.innerHTML = `
            <h4 class="text-sm font-bold text-[#1a233a] border-b border-slate-200 pb-2 mb-4">Batch Job Configuration</h4>
            <label class="${labelClasses}">SFTP Hostname / IP:</label>
            <input type="text" id="batch-host" value="${existingData.host || ''}" placeholder="sftp.bank.com" class="${inputClasses}">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="${labelClasses}">Cron Schedule:</label>
                    <input type="text" id="batch-cron" value="${existingData.cron || ''}" placeholder="0 0 * * *" class="${inputClasses}">
                </div>
                <div>
                    <label class="${labelClasses}">File Format:</label>
                    <select id="batch-format" class="${inputClasses}">
                        <option value="CSV" ${existingData.format === 'CSV' ? 'selected' : ''}>CSV</option>
                        <option value="XML" ${existingData.format === 'XML' ? 'selected' : ''}>XML</option>
                        <option value="JSON" ${existingData.format === 'JSON' ? 'selected' : ''}>JSON</option>
                    </select>
                </div>
            </div>
        `;
    } else {
        container.innerHTML = `<p class="text-slate-500 text-sm italic text-center py-4">Select an integration approach above to configure technical details.</p>`;
    }
}

async function saveTechDetails() {
    const id = window.currentEditingTechId;
    const tp = window.phase2DataMap[id];
    const integrationType = document.getElementById('tech-integration-type').value;
    
    // 1. Harvest the Dynamic JSON Data
    let detailsJson = {};
    if (integrationType === 'api') {
        detailsJson = {
            url: document.getElementById('api-url').value,
            method: document.getElementById('api-method').value,
            auth: document.getElementById('api-auth').value
        };
    } else if (integrationType === 'database') {
        detailsJson = {
            schema: document.getElementById('db-schema').value,
            engine: document.getElementById('db-engine').value,
            object: document.getElementById('db-object').value
        };
    } else if (integrationType === 'batch') {
        detailsJson = {
            host: document.getElementById('batch-host').value,
            cron: document.getElementById('batch-cron').value,
            format: document.getElementById('batch-format').value
        };
    }

    // 2. Package the payload exactly like our inline save (so dates aren't lost)
    const payload = {
        integration: integrationType,
        start: tp.start,
        end: tp.end,
        technical_details: detailsJson
    };

    // 3. Send to Postgres
    try {
        const response = await fetch(`/api/phase2/update/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            alert("Technical Blueprint Saved Successfully!");
            closeTechDetail(); // Back to dashboard, triggering a fresh fetch
        } else {
            alert("Failed to save blueprint. Check terminal logs.");
        }
    } catch (err) {
        console.error("Save failed:", err);
        alert("Network error.");
    }
}

// ==========================================
// AUTO-LOADER (Bypasses Navigation Conflicts)
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    populateTechTable();
});

const phase2Btn = document.getElementById('nav-2');
if (phase2Btn) {
    phase2Btn.addEventListener('click', () => {
        populateTechTable();
    });
}
async function triggerWorkshopInvites() {
    const btn = document.getElementById('btn-send-invites');
    const originalHTML = btn.innerHTML;
    
    // UI Feedback: Show loading state
    btn.innerHTML = `<svg class="animate-spin h-4 w-4 text-white inline mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Sending...`;
    btn.disabled = true;
    btn.classList.add('opacity-75', 'cursor-wait');

    try {
        const response = await fetch('/api/phase2/trigger-invites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === "success") {
            if (data.emails_sent > 0) {
                alert(`Success! Generated and sent ${data.emails_sent} workshop invites for tomorrow.`);
            } else {
                alert(`Notice: ${data.message}`);
            }
        } else {
            alert("Error sending invites: " + data.message);
        }
    } catch (err) {
        console.error("Invite trigger failed:", err);
        alert("Network error. Could not connect to server.");
    } finally {
        // Restore button state
        btn.innerHTML = originalHTML;
        btn.disabled = false;
        btn.classList.remove('opacity-75', 'cursor-wait');
    }
}

// ==========================================
// NEW: RGT / API TEMPLATE DISPATCHER
// ==========================================
async function triggerApiRequirementTemplates() {
    // Make sure your button in HTML has the ID 'sendApiTemplatesBtn' and an onclick="triggerApiRequirementTemplates()"
    const btn = document.getElementById('sendApiTemplatesBtn');
    const originalHTML = btn ? btn.innerHTML : 'Send API Requirement Templates';
    
    if (btn) {
        btn.innerHTML = `<svg class="animate-spin h-4 w-4 text-white inline mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Processing Templates...`;
        btn.disabled = true;
        btn.classList.add('opacity-75', 'cursor-wait');
    }

    try {
        // 1. Get current project
        const project = document.getElementById('projectSelector')?.value;
        if (!project) {
            alert("Please select a project first.");
            return;
        }

        // 2. Send request — backend filters for tomorrow's API touchpoints
        const response = await fetch(`/api/touchpoints/dispatch-tomorrow-rgts/${project}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();
        
        if (response.ok) {
            const { successful, skipped, failed } = data.summary || {successful: [], skipped: [], failed: []};
            alert(`Batch Complete!\n\n✅ Sent Templates: ${successful.length}\n⏭️ Skipped Non-APIs: ${skipped.length}\n❌ Failed: ${failed.length}`);
        } else {
            alert("Error dispatching templates: " + (data.message || "Unknown error"));
        }
    } catch (err) {
        console.error("Template dispatch failed:", err);
        alert("Network error. Could not connect to server.");
    } finally {
        // Restore button state
        if (btn) {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
            btn.classList.remove('opacity-75', 'cursor-wait');
        }
    }
}
async function triggerInboxSync() {
    const btn = document.getElementById('syncInboxBtn');
    const originalHTML = btn.innerHTML;
    
    btn.innerHTML = `Scanning Inbox...`;
    btn.disabled = true;
    btn.classList.add('opacity-75', 'cursor-wait');

    try {
        const response = await fetch('/api/touchpoints/sync-inbox');
        const data = await response.json();
        
        if (response.ok) {
            alert(data.message);
            populateTechTable(); // Refresh the table to show the new "In Progress" status!
        } else {
            alert("Error syncing inbox: " + data.message);
        }
    } catch (err) {
        console.error("Sync failed:", err);
        alert("Network error. Could not connect to server.");
    } finally {
        btn.innerHTML = originalHTML;
        btn.disabled = false;
        btn.classList.remove('opacity-75', 'cursor-wait');
    }
}

// ==========================================
// PHASE 2 FILTERS
// ==========================================

// Stores the last-applied filter values (so Cancel can revert)
window._p2FilterSnapshot = { name: '', status: 'ALL', type: 'ALL', module: 'ALL', owner: 'ALL' };

window.matchesPhase2Filters = function(tp) {
    const nameFilter = (document.getElementById('p2-filter-name')?.value || '').trim().toLowerCase();
    const statusFilter = document.getElementById('p2-filter-status')?.value || 'ALL';
    const typeFilter = document.getElementById('p2-filter-type')?.value || 'ALL';
    const moduleFilter = document.getElementById('p2-filter-module')?.value || 'ALL';
    const ownerFilter = document.getElementById('p2-filter-owner')?.value || 'ALL';

    if (nameFilter && !(tp.name || '').toLowerCase().includes(nameFilter)) return false;
    if (statusFilter !== 'ALL' && tp.techStatus !== statusFilter) return false;
    if (typeFilter !== 'ALL' && (tp.integration || 'unassigned') !== typeFilter) return false;
    if (moduleFilter !== 'ALL' && tp.module !== moduleFilter) return false;
    if (ownerFilter !== 'ALL') {
        const rawOwner = tp.owner || '';
        const ownerOnly = rawOwner.includes('(') ? rawOwner.split(' (')[0].trim() : rawOwner.trim();
        if (ownerOnly !== ownerFilter) return false;
    }
    return true;
};

function clearPhase2Filters() {
    const n = document.getElementById('p2-filter-name');
    const s = document.getElementById('p2-filter-status');
    const t = document.getElementById('p2-filter-type');
    const m = document.getElementById('p2-filter-module');
    const o = document.getElementById('p2-filter-owner');
    if (n) n.value = '';
    if (s) s.value = 'ALL';
    if (t) t.value = 'ALL';
    if (m) m.value = 'ALL';
    if (o) o.value = 'ALL';
    window._p2FilterSnapshot = { name: '', status: 'ALL', type: 'ALL', module: 'ALL', owner: 'ALL' };
    // Close dropdown and re-render
    const menu = document.getElementById('phase2FilterMenu');
    if (menu) menu.classList.add('hidden');
    populateTechTable();
}

// Called when user clicks "Apply" inside the filter dropdown
function applyPhase2Filters() {
    // Snapshot current selections so Cancel can restore them
    window._p2FilterSnapshot = {
        name: (document.getElementById('p2-filter-name')?.value || '').trim(),
        status: document.getElementById('p2-filter-status')?.value || 'ALL',
        type: document.getElementById('p2-filter-type')?.value || 'ALL',
        module: document.getElementById('p2-filter-module')?.value || 'ALL',
        owner: document.getElementById('p2-filter-owner')?.value || 'ALL'
    };
    // Close the dropdown
    const menu = document.getElementById('phase2FilterMenu');
    if (menu) menu.classList.add('hidden');
    // Re-render table with filters
    populateTechTable();
}

// Called when user clicks "Cancel" inside the filter dropdown
function cancelPhase2Filters() {
    // Revert inputs/selects to last-applied snapshot
    const snap = window._p2FilterSnapshot;
    const n = document.getElementById('p2-filter-name');
    const s = document.getElementById('p2-filter-status');
    const t = document.getElementById('p2-filter-type');
    const m = document.getElementById('p2-filter-module');
    const o = document.getElementById('p2-filter-owner');
    if (n) n.value = snap.name;
    if (s) s.value = snap.status;
    if (t) t.value = snap.type;
    if (m) m.value = snap.module;
    if (o) o.value = snap.owner;
    // Close the dropdown (no re-render, table stays as-is)
    const menu = document.getElementById('phase2FilterMenu');
    if (menu) menu.classList.add('hidden');
}

// Toggle the Filter dropdown panel open/closed
function togglePhase2Filter(event) {
    event.stopPropagation();
    const menu = document.getElementById('phase2FilterMenu');
    if (menu) menu.classList.toggle('hidden');
    // Close Actions menu if open
    const actionsMenu = document.getElementById('phase2ActionsMenu');
    if (actionsMenu) actionsMenu.classList.add('hidden');
}

// Populate the Module + Owner filter dropdowns dynamically after data loads,
// then restore all filter inputs from the snapshot so selections persist.
function updatePhase2ModuleFilter() {
    const moduleSelect = document.getElementById('p2-filter-module');
    const ownerSelect = document.getElementById('p2-filter-owner');
    const modules = new Set();
    const owners = new Set();

    // Collect ALL unique values from full dataset (not filtered subset)
    Object.values(window.phase2DataMap).forEach(tp => {
        if (tp.module && tp.module.trim()) modules.add(tp.module.trim());
        const rawOwner = tp.owner || '';
        const ownerOnly = rawOwner.includes('(') ? rawOwner.split(' (')[0].trim() : rawOwner.trim();
        if (ownerOnly && ownerOnly !== 'Unassigned') owners.add(ownerOnly);
    });

    // Rebuild Module dropdown options
    if (moduleSelect) {
        let html = '<option value="ALL">All Modules</option>';
        Array.from(modules).sort().forEach(m => {
            html += `<option value="${m}">${m}</option>`;
        });
        moduleSelect.innerHTML = html;
    }

    // Rebuild Owner dropdown options
    if (ownerSelect) {
        let html = '<option value="ALL">All Owners</option>';
        Array.from(owners).sort().forEach(o => {
            html += `<option value="${o}">${o}</option>`;
        });
        ownerSelect.innerHTML = html;
    }

    // --- RESTORE all filter values from the snapshot ---
    // This ensures that after dropdowns are rebuilt, previously-applied
    // selections stay visible when the user re-opens the filter panel.
    restorePhase2FilterSnapshot();
}

// Writes the snapshot values back into all filter DOM elements
function restorePhase2FilterSnapshot() {
    const snap = window._p2FilterSnapshot;
    const n = document.getElementById('p2-filter-name');
    const s = document.getElementById('p2-filter-status');
    const t = document.getElementById('p2-filter-type');
    const m = document.getElementById('p2-filter-module');
    const o = document.getElementById('p2-filter-owner');
    if (n) n.value = snap.name;
    if (s) s.value = snap.status;
    if (t) t.value = snap.type;
    if (m) m.value = snap.module;
    if (o) o.value = snap.owner;
}

// ==========================================
// CLICK-OUTSIDE-CLOSE FOR DROPDOWNS
// ==========================================
function togglePhase2Actions(event) {
    event.stopPropagation();
    const menu = document.getElementById('phase2ActionsMenu');
    if (menu) menu.classList.toggle('hidden');
    // Close Filter menu if open
    const filterMenu = document.getElementById('phase2FilterMenu');
    if (filterMenu) filterMenu.classList.add('hidden');
}

document.addEventListener('click', function(e) {
    // Close Actions menu
    const actionsMenu = document.getElementById('phase2ActionsMenu');
    const actionsWrapper = document.getElementById('phase2ActionsWrapper');
    if (actionsMenu && actionsWrapper && !actionsWrapper.contains(e.target)) {
        actionsMenu.classList.add('hidden');
    }
    // Close Filter menu
    const filterMenu = document.getElementById('phase2FilterMenu');
    const filterWrapper = document.getElementById('phase2FilterWrapper');
    if (filterMenu && filterWrapper && !filterWrapper.contains(e.target)) {
        filterMenu.classList.add('hidden');
    }
});