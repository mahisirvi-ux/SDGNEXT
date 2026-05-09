// ==========================================
// GLOBAL STATE MANAGEMENT
// ==========================================
window.phase2DataMap = {}; 
window.currentEditingTechId = null;

// ==========================================
// MASTER NAVIGATION LOGIC (Sidebar)
// ==========================================
function switchPhase(phaseNumber) {
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

        populateTechTable(); 
    }
    else if (phaseNumber === 3) {
        document.getElementById('phase3-board').classList.remove('hidden');
        document.getElementById('phase3-board').classList.add('flex');
        document.getElementById('nav-3').classList.remove('text-slate-400', 'hover:text-white', 'hover:bg-slate-700');
        document.getElementById('nav-3').classList.add('bg-pink-500', 'text-white');
    }
}

// ==========================================
// PHASE 2: REAL DATA FETCHING & RENDERING
// ==========================================
async function populateTechTable() {
    const tbody = document.getElementById('tech-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="8" class="px-5 py-8 text-center text-sm font-medium text-slate-400">Loading live data from database...</td></tr>';
    try {
        const response = await fetch('/api/phase2/dashboard?t=' + new Date().getTime());
        const result = await response.json();
        const eligibleItems = result.data || [];

        let countPending = 0;
        let countScheduled = 0;
        let countRescheduled = 0; // <--- NEW: Initialize Counter
        let countInProgress = 0;
        let countDelayed = 0;
        // ---------------------------------

        if (eligibleItems.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="px-5 py-8 text-center text-sm text-slate-500 italic">No touchpoints have been signed off in Phase 1 yet.</td></tr>`;
            
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

        eligibleItems.forEach(tp => {
            window.phase2DataMap[tp.id] = tp; 

            // --- COUNT THE CORRECT STATUSES ---
            if (tp.techStatus === 'Pending Workshop') countPending++;
            if (tp.techStatus === 'Scheduled') countScheduled++;
            if (tp.techStatus === 'Rescheduled') countRescheduled++; // <--- NEW: Count the status
            if (tp.techStatus === 'In Progress') countInProgress++;
            if (tp.techStatus === 'Delayed') countDelayed++;

            const tr = document.createElement('tr');
            tr.className = "hover:bg-slate-50 transition-colors border-b border-slate-100";
            const safeStart = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start : "";
            const safeEnd = (tp.end && tp.end !== "-" && tp.end !== "None") ? tp.end : "";
            
            const rawOwner = tp.owner || "Unassigned";
            const ownerOnly = typeof rawOwner === 'string' && rawOwner.includes('(') 
                ? rawOwner.split(' (')[0].trim() 
                : rawOwner;

            // --- THESE ARE THE TWO LINES THAT WENT MISSING! ---
           // --- NEW: Safe Integration Logic ---
            const safeIntegration = tp.integration || 'unassigned';
            const integrationDisplay = safeIntegration === 'unassigned' 
                ? '<span class="text-slate-400 italic text-xs">Pending Workshop</span>' 
                : `<span class="capitalize font-medium text-slate-700">${safeIntegration}</span>`;

            // Setup the selected state for the new Integration Dropdown
            const isApi = safeIntegration.toLowerCase() === 'api' ? 'selected' : '';
            const isDb = safeIntegration.toLowerCase() === 'database' ? 'selected' : '';
            const isUnassignedInteg = (!isApi && !isDb) ? 'selected' : '';
            // ------------------------------------

            const isCompleted = tp.techStatus === 'Completed' ? 'selected' : '';
            const isRescheduled = tp.techStatus === 'Rescheduled' ? 'selected' : '';
            const isAuto = (!isCompleted && !isRescheduled) ? 'selected' : '';

            tr.innerHTML = `
                <td class="px-5 py-4 text-sm font-bold text-slate-800 group">
                    <button onclick="window.location.href='/details?id=${tp.id}'" class="text-[#1a233a] hover:text-indigo-600 transition-colors text-left flex items-center gap-2">
                        ${tp.name}
                        <svg class="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                    </button>
                </td>
                
                <td class="px-5 py-4 text-sm text-slate-600">${tp.module}</td>
                
                <td class="px-5 py-4 text-sm">
                    <div id="integ-view-${tp.id}">
                        ${integrationDisplay}
                    </div>
                    <select id="integ-edit-${tp.id}" class="hidden text-xs border border-slate-300 rounded p-1 shadow-sm bg-white w-full max-w-[120px]">
                        <option value="unassigned" ${isUnassignedInteg}>Unassigned</option>
                        <option value="api" ${isApi}>API</option>
                        <option value="database" ${isDb}>Database</option>
                    </select>
                </td>
                
                <td class="px-5 py-4 text-sm text-slate-600">${ownerOnly}</td>
                
                <td class="px-5 py-4">
                    <input type="date" id="start-${tp.id}" value="${safeStart}" class="text-xs border border-slate-300 rounded p-1.5 shadow-sm bg-slate-50 disabled:opacity-60 disabled:cursor-not-allowed" disabled>
                </td>
                
                <td class="px-5 py-4">
                    <input type="date" id="end-${tp.id}" value="${safeEnd}" class="text-xs border border-slate-300 rounded p-1.5 shadow-sm bg-slate-50 disabled:opacity-60 disabled:cursor-not-allowed" disabled>
                </td>
                
                <td class="px-5 py-4 whitespace-nowrap">
                    <span id="status-pill-${tp.id}" class="px-2.5 py-1 text-[10px] uppercase font-bold rounded-full border ${tp.statusClass}">${tp.techStatus}</span>
                    
                    <select id="status-edit-${tp.id}" class="hidden text-xs border border-slate-300 rounded p-1 shadow-sm bg-white w-full max-w-[120px]">
                        <option value="Auto" ${isAuto}>Auto-Calculate</option>
                        <option value="Completed" ${isCompleted}>Completed</option>
                        <option value="Rescheduled" ${isRescheduled}>Rescheduled</option>
                    </select>
                </td>
                
                <td class="px-5 py-4 text-right min-w-[140px]">
                    <button onclick="window.location.href='/details?id=${tp.id}'" class="text-indigo-600 hover:text-indigo-800 text-xs font-bold transition-colors mr-3">Specs</button>
                    <button id="edit-btn-${tp.id}" onclick="enableEditMode(${tp.id})" class="text-blue-600 hover:text-blue-800 text-xs font-bold transition-colors">Edit</button>
                    <button id="save-btn-${tp.id}" onclick="saveRowChanges(${tp.id})" class="hidden bg-emerald-500 hover:bg-emerald-600 text-white text-[10px] uppercase font-bold py-1.5 px-3 rounded shadow-sm transition-all">Save</button>
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
    } catch (error) {
        console.error("Error fetching live Phase 2 data:", error);
        tbody.innerHTML = `<tr><td colspan="8" class="px-5 py-8 text-center text-sm font-bold text-red-500">Failed to load data.</td></tr>`;
    }
}

// ==========================================
// INLINE EDITING LOGIC (Control Tower)
// ==========================================
function enableEditMode(touchpointId) {
    document.getElementById(`start-${touchpointId}`).disabled = false;
    document.getElementById(`end-${touchpointId}`).disabled = false;
    
    document.getElementById(`start-${touchpointId}`).classList.replace('bg-slate-50', 'bg-white');
    document.getElementById(`end-${touchpointId}`).classList.replace('bg-slate-50', 'bg-white');

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

    const payload = {
        // --- THIS IS THE CRITICAL FIX ---
        // Grab the value from the newly visible edit dropdown
        integration: document.getElementById(`integ-edit-${touchpointId}`).value,
        // --------------------------------
        
        start: document.getElementById(`start-${touchpointId}`).value,
        end: document.getElementById(`end-${touchpointId}`).value,
        
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
    btn.innerHTML = `<svg class="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Sending...`;
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