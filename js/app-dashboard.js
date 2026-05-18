let globalTrackerData = [];
let globalActiveTouchpointId = null;

document.addEventListener('DOMContentLoaded', async () => {
    const fileInput = document.getElementById('csvFileInput');
    const projectSelector = document.getElementById('projectSelector');

    // Parse project id from URL (/project?id=X)
    const urlParams = new URLSearchParams(window.location.search);
    const projectId = urlParams.get('id');

    // If no id param, redirect to landing
    if (!projectId) {
        window.location.replace('/');
        return;
    }

    // Load projects and find the matching one
    let projects = [];
    try {
        const response = await fetch('/projects');
        if (!response.ok) throw new Error('Backend error');
        projects = await response.json();
    } catch (err) {
        document.getElementById('tracker-table-body').innerHTML =
            '<tr><td colspan="7" class="p-8 text-center text-red-400">Failed to load projects. <button onclick="location.reload()" class="underline text-indigo-500">Retry</button></td></tr>';
        return;
    }

    const matchedProject = projects.find(p => p.id === parseInt(projectId));
    console.log('[SDGNext] URL id:', projectId, '→ matched:', matchedProject?.project_name, '| projects:', projects.map(p => p.id + ':' + p.project_name));
    if (!matchedProject) {
        window.location.replace('/');
        return;
    }

                // Populate dropdown and select matching project
    projectSelector.innerHTML = '';
    projects.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.project_name;
        opt.dataset.id = p.id;
        opt.innerText = p.project_name;
        if (p.id === matchedProject.id) opt.selected = true;
        projectSelector.appendChild(opt);
    });
    projectSelector.value = matchedProject.project_name;

    window.currentProjectName = matchedProject.project_name;
    await loadData(matchedProject.project_name);

    // Handle navigation from details page with phase preference
    const savedPhase = localStorage.getItem('activePhase');
    if (savedPhase) {
        localStorage.removeItem('activePhase');
        setTimeout(() => {
            if (typeof switchPhase === 'function') {
                switchPhase(parseInt(savedPhase));
            }
        }, 300);
    }

        // Listeners
    projectSelector.addEventListener('change', (e) => {
    if (e.target.value) {
        window.currentProjectName = e.target.value;
        // Update URL with new project id
        const selectedOpt = e.target.selectedOptions[0];
        const newId = selectedOpt.dataset.id;
        history.pushState({}, '', `/project?id=${newId}`);
        if(typeof window.closeFlyout === 'function') window.closeFlyout();
        loadData(e.target.value);
        // If Phase 2 board is currently visible, refresh it for the new project
        if (typeof populateTechTable === 'function') {
            const phase2Board = document.getElementById('phase2-board');
            if (phase2Board && !phase2Board.classList.contains('hidden')) {
                populateTechTable();
            }
        }
    } else {
        showEmptyState();
    }
    });

    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file || !projectSelector.value) return;

        const statusText = document.getElementById('lastUpdatedText');
        if(statusText) statusText.innerText = `Uploading Phase 1 Data...`;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`/upload-csv/${projectSelector.value}`, {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                if(statusText) statusText.innerText = `Saved successfully!`;
                await loadData(projectSelector.value);
            } else {
                alert(`Upload failed. Check terminal for errors.`);
                if(statusText) statusText.innerText = `Upload Failed`;
            }
        } catch (error) {
            console.error("Upload error:", error);
            alert("Could not connect to backend to upload.");
        }
        fileInput.value = '';
    });
    // ==========================================
    // IDENTITY MASTER UPLOADS (Departments + Team Members)
    // ==========================================
    // Generic uploader that posts a file to a target URL, shows status, reloads on success.
    async function uploadIdentityCsv(file, url, label) {
        const statusText = document.getElementById('lastUpdatedText');
        if (statusText) statusText.innerText = `Uploading ${label}...`;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(url, { method: 'POST', body: formData });
            const result = await response.json();

            if (response.ok) {
                // Build a friendly recap from the response
                let summary = result.message || `${label} uploaded.`;
                if (result.skipped_rows && Array.isArray(result.skipped_rows) && result.skipped_rows.length) {
                    summary += `\n\n⚠️ ${result.skipped_rows.length} row(s) were skipped.`;
                    const first3 = result.skipped_rows.slice(0, 3).map(r => r.reason || 'invalid').join('\n  - ');
                    summary += `\n  - ${first3}`;
                }
                alert(summary);
                if (statusText) statusText.innerText = `${label} updated.`;

                // Reload so all dropdowns rebuild against fresh data
                setTimeout(() => window.location.reload(), 1000);
            } else {
                alert(`${label} upload failed: ${result.detail || result.message || 'unknown error'}`);
                if (statusText) statusText.innerText = `${label} upload failed.`;
            }
        } catch (err) {
            console.error(`${label} upload error:`, err);
            alert(`Network error during ${label.toLowerCase()} upload.`);
        }
    }

        // Departments
    const departmentsInput = document.getElementById('departmentsCsvInput');
    if (departmentsInput) {
        departmentsInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const project = document.getElementById('projectSelector')?.value;
            if (!project) { alert('Please select a project first!'); departmentsInput.value = ''; return; }
            await uploadIdentityCsv(file, `/upload-departments/${project}`, 'Departments');
            departmentsInput.value = '';
        });
    }

    // Team Members
    const teamMembersInput = document.getElementById('teamMembersCsvInput');
    if (teamMembersInput) {
        teamMembersInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const project = document.getElementById('projectSelector')?.value;
            if (!project) { alert('Please select a project first!'); teamMembersInput.value = ''; return; }
            await uploadIdentityCsv(file, `/upload-team-members/${project}`, 'Team Members');
            teamMembersInput.value = '';
        });
    }

    // Legacy teamLovInput (the old "Manage Teams" file input). Still in the DOM
    // for backward compat with any third-party scripts; surfaces a clear message
    // explaining the new flow if it ever fires.
    const legacyTeamInput = document.getElementById('teamLovInput');
    if (legacyTeamInput) {
        legacyTeamInput.addEventListener('change', () => {
            alert(
                "The 'Manage Teams' upload has been replaced.\n\n" +
                "Use 'Manage Identities' → Upload Departments first, then Upload Team Members.\n" +
                "If you need a starting point, click 'Download Migration Template'."
            );
            legacyTeamInput.value = '';
        });
    }
});

// --- API CALLS & DATA PREP ---

async function populateProjectsDropdown(selector) {
    try {
        const response = await fetch('/projects');
        if (!response.ok) throw new Error("Backend returned an error");
        
        const projects = await response.json();
        selector.innerHTML = '';

        if (projects.length === 0) {
            selector.innerHTML = '<option value="">-- Create DB Project --</option>';
            return;
        }

        projects.forEach(p => {
            const opt = document.createElement('option');
            const pName = p.project_name || p.name; 
            opt.value = pName;
            opt.innerText = pName;
            selector.appendChild(opt);
        });
    } catch (error) {
        console.error("DB Connection Error:", error);
        selector.innerHTML = '<option value="">Error Loading Projects</option>';
        showEmptyState();
    }
}

async function loadPendingOptions() {
    try {
        const project = document.getElementById('projectSelector')?.value;
        const url = project ? `/pending-options/${project}` : '/pending-options';
        const response = await fetch(url);
        if (!response.ok) return;

        const options = await response.json();
        const select = document.getElementById('log-pending');
        if (!select) return;

        let html = '<option value="">-- Pending With (None) --</option>';

        if (Array.isArray(options) && options.length > 0) {
            // Detect response shape: new endpoint returns rich objects with .display.
            // Legacy fallback: a plain array of strings.
            const isRich = typeof options[0] === 'object' && options[0] !== null && 'display' in options[0];

            if (isRich) {
                options.forEach(opt => {
                    const val = (opt.display || opt.full_name || '').replace(/"/g, '&quot;');
                    const label = (opt.display_with_dept || opt.display || '').replace(/</g, '&lt;');
                    html += `<option value="${val}">${label}</option>`;
                });
            } else {
                // Legacy: plain strings
                options.forEach(opt => {
                    const safe = String(opt).replace(/"/g, '&quot;');
                    html += `<option value="${safe}">${safe}</option>`;
                });
            }
        }

        select.innerHTML = html;
    } catch (error) {
        console.error("Error fetching pending options:", error);
    }
}

function updateFilterDropdowns() {
    if (!globalTrackerData || globalTrackerData.length === 0) return;

    const modules = new Set();
    const owners = new Set();
    const statuses = new Set();

    // Extract unique values from our dataset
    globalTrackerData.forEach(row => {
        if (row.module && row.module.trim() !== "") modules.add(row.module.trim());
        if (row.technical_owner && row.technical_owner.trim() !== "") owners.add(row.technical_owner.trim());
        if (row.idr_status && row.idr_status.trim() !== "") statuses.add(row.idr_status.trim());
    });

    const populateSelect = (id, defaultText, items) => {
        const select = document.getElementById(id);
        if (!select) return;
        
        const currentVal = select.value; // Remember user's selection
        let html = `<option value="ALL">${defaultText}</option>`;
        
        Array.from(items).sort().forEach(item => {
            html += `<option value="${item}">${item}</option>`;
        });
        
        select.innerHTML = html;
        if (items.has(currentVal)) select.value = currentVal;
    };

    populateSelect('filter-module', 'All Modules', modules);
    populateSelect('filter-owner', 'All Tech Owners', owners);
    populateSelect('filter-status', 'All Statuses', statuses);
}

async function loadData(projectCode) {
    try {
        const response = await fetch(`/tasks/${projectCode}`);
        if (!response.ok) throw new Error("Failed to fetch tasks");
        
        const data = await response.json();

        if (data && data.length > 0) {
            globalTrackerData = data;
            
            // 1. Load the backend dropdowns
            await loadPendingOptions();
            
            // 2. Build the top filter bars based on the fetched data
            updateFilterDropdowns();
            
            // 3. Render the main table
            window.renderPhase1Dashboard();
        } else {
            globalTrackerData = [];
            showEmptyState();
        }
    } catch (error) {
        console.error("Backend unreachable or error loading data:", error);
        showEmptyState();
    }
}

// --- RENDERING LOGIC ---

function showEmptyState() {
    const emptyState = document.getElementById('empty-state');
    const board = document.getElementById('phase1-board');
    if(emptyState) {
        emptyState.classList.remove('hidden');
        emptyState.classList.add('flex');
    }
    if(board) board.classList.add('hidden');
}

function getStatusColor(status) {
    const s = (status || '').toLowerCase();
    if (s.includes('signed-off')) return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    if (s.includes('pending')) return 'bg-amber-100 text-amber-800 border-amber-200';
    if (s.includes('hold')) return 'bg-red-100 text-red-800 border-red-200';
    return 'bg-slate-100 text-[#1a233a] border-slate-300';
}

window.clearFilters = function() {
    if(document.getElementById('filter-module')) document.getElementById('filter-module').value = 'ALL';
    if(document.getElementById('filter-owner')) document.getElementById('filter-owner').value = 'ALL';
    if(document.getElementById('filter-status')) document.getElementById('filter-status').value = 'ALL';
    window.renderPhase1Dashboard();
};

window.renderPhase1Dashboard = function() {
    if (!globalTrackerData || globalTrackerData.length === 0) return;

    const emptyState = document.getElementById('empty-state');
    const board = document.getElementById('phase1-board');
    if(emptyState) {
        emptyState.classList.add('hidden');
        emptyState.classList.remove('flex');
    }

    // Only un-hide phase1-board if Phase 1 is the active tab. If user is on
    // Phase 2 or 3, we still want the data fetched & cached, but the board
    // itself must stay hidden until the user navigates back to Phase 1.
    const phase2Active = !document.getElementById('phase2-board')?.classList.contains('hidden');
    const phase3Active = !document.getElementById('phase3-board')?.classList.contains('hidden');
    if (board && !phase2Active && !phase3Active) {
        board.classList.remove('hidden');
    }

    // KPI Summary Cards
    const total = globalTrackerData.length;
    const signedOff = globalTrackerData.filter(d => (d.idr_status || '').toLowerCase().includes('signed-off')).length;
    const pending = globalTrackerData.filter(d => (d.idr_status || '').toLowerCase().includes('pending')).length;
    const inProgress = total - signedOff - pending;

    const setKPI = (id, val) => { const el = document.getElementById(id); if(el) el.innerText = val; };
    setKPI('kpi-total', total);
    setKPI('kpi-progress', inProgress);
    setKPI('kpi-pending', pending);
    setKPI('kpi-ready', signedOff);

    // Filter Logic
    const modFilter = document.getElementById('filter-module')?.value || 'ALL';
    const ownerFilter = document.getElementById('filter-owner')?.value || 'ALL';
    const statusFilter = document.getElementById('filter-status')?.value || 'ALL';

    const filteredData = globalTrackerData.filter(row => {
        const matchMod = modFilter === 'ALL' || (row.module === modFilter);
        const matchOwner = ownerFilter === 'ALL' || (row.technical_owner === ownerFilter);
        const matchStatus = statusFilter === 'ALL' || (row.idr_status === statusFilter);
        return matchMod && matchOwner && matchStatus;
    });

    const table = document.getElementById('idr-table');
    if (!table) return;

    let html = `
        <thead class="bg-slate-50 text-[#1a233a] text-xs uppercase tracking-wider border-b border-slate-200">
            <tr>
                <th class="px-5 py-4 font-semibold">Touchpoint Name</th>
                <th class="px-5 py-4 font-semibold">Module</th>
                <th class="px-5 py-4 font-semibold">Technical Owner</th>
                <th class="px-5 py-4 font-semibold">IDR Status</th>
            </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
    `;

    if (filteredData.length === 0) {
        html += `<tr><td colspan="4" class="px-5 py-8 text-center text-sm text-slate-400 font-medium">No touchpoints match your selected filters.</td></tr>`;
    } else {
        filteredData.forEach(row => {
            const originalIndex = globalTrackerData.indexOf(row);
            const tp = row.integration_touch_point || 'Unnamed';
            const mod = row.module || '-';
            const owner = row.technical_owner || '-';
            const status = row.idr_status || 'In-Progress';
            const badgeColor = getStatusColor(status);

            html += `
                <tr class="hover:bg-slate-50 cursor-pointer transition-colors" onclick="openFlyout(${originalIndex})">
                    <td class="px-5 py-4 text-sm font-semibold text-[#1a233a] whitespace-nowrap">${tp}</td>
                    <td class="px-5 py-4 text-sm text-slate-600">${mod}</td>
                    <td class="px-5 py-4 text-sm text-slate-600">${owner}</td>
                    <td class="px-5 py-4 text-sm">
                        <span class="px-2.5 py-1 rounded-full text-xs font-bold border ${badgeColor}">${status}</span>
                    </td>
                </tr>
            `;
        });
    }

    html += '</tbody>';
    table.innerHTML = html;
}

// --- WINDOW GLOBALS (ATTACHED FOR HTML CLICKS) ---

window.openFlyout = function(dataIndex) {
    const data = globalTrackerData[dataIndex];
    if (!data) return;
    globalActiveTouchpointId = data.id;

    const setVal = (id, val) => { const el = document.getElementById(id); if(el) el.innerText = val; };

    setVal('flyout-module', data.module || 'UNKNOWN MODULE');
    setVal('flyout-title', data.integration_touch_point || 'Unnamed Touchpoint');
    setVal('flyout-source', data.source_system || '-');
    setVal('flyout-target', data.target_system || '-');
    setVal('flyout-flow', data.business_flow || '-');

    // Owner: prefer the enriched 'Name (Department)' from the new identity model,
    // fall back to raw owner if backend predates the refactor.
        setVal('flyout-owner', data.owner_display || data.owner || 'Unassigned');
    setVal('flyout-inputs', data.inputs || '-');
    setVal('flyout-outputs', data.expected_output || '-');
    // Pending: same enrichment treatment so the badge reads 'Rahul (CBS)'.
    setVal('flyout-pending', data.pending_with_display || data.pending_with || 'None');
    setVal('flyout-signoff', data.idr_signoff_date || 'Pending');

    const statusEl = document.getElementById('flyout-status');
    const statusTxt = data.idr_status || 'In-Progress';
    if(statusEl) {
        statusEl.innerText = statusTxt;
        statusEl.className = `inline-flex px-3 py-1 text-xs border uppercase tracking-wider font-extrabold rounded-md ${getStatusColor(statusTxt)}`;
    }

    // Render Split Timelines
    const pointersEl = document.getElementById('flyout-pointers-timeline');
    const remarksEl = document.getElementById('flyout-remarks-timeline');

    if (pointersEl) {
        if (data.pointers_timeline && data.pointers_timeline.length > 0) {
            let p_html = '';
            data.pointers_timeline.forEach(log => {
                p_html += `
                    <div class="relative pb-3">
                        <div class="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-amber-400 ring-4 ring-white"></div>
                        <p class="text-[10px] font-bold text-slate-400 mb-0.5">${log.created_at}</p>
                        <p class="text-sm font-medium text-slate-700 bg-white p-2 rounded-md border border-slate-200 shadow-sm">${log.comment}</p>
                    </div>
                `;
            });
            pointersEl.innerHTML = p_html;
        } else {
            pointersEl.innerHTML = '<p class="text-xs text-slate-400 italic mb-4">No open pointers history.</p>';
        }
    }

    if (remarksEl) {
        if (data.remarks_timeline && data.remarks_timeline.length > 0) {
            let r_html = '';
            data.remarks_timeline.forEach(log => {
                r_html += `
                    <div class="relative pb-3">
                        <div class="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-pink-500 ring-4 ring-white"></div>
                        <p class="text-xs font-bold text-[#1a233a]">${log.action_by} <span class="font-medium text-slate-400 ml-2 text-[10px]">${log.created_at}</span></p>
                        <p class="text-sm text-slate-600 mt-1">${log.comment}</p>
                    </div>
                `;
            });
            remarksEl.innerHTML = r_html;
        } else {
            remarksEl.innerHTML = '<p class="text-xs text-slate-400 italic mb-4">No remarks logged yet.</p>';
        }
    }

    // Reset inputs
    if(document.getElementById('log-comment')) document.getElementById('log-comment').value = '';
    if(document.getElementById('log-status')) document.getElementById('log-status').value = '';
    if(document.getElementById('log-pending')) document.getElementById('log-pending').value = data.pending_with || '';
    if(document.getElementById('log-pointers')) document.getElementById('log-pointers').value = '';

    // Reset Accordion to default state
    if(typeof window.toggleAccordion === 'function') {
        window.toggleAccordion('acc-pointers');
        const accPointers = document.getElementById('acc-pointers');
        if(accPointers) accPointers.classList.remove('hidden');
    }

    const panel = document.getElementById('slideOutPanel');
    if(panel) panel.classList.remove('translate-x-full');
};

window.closeFlyout = function() {
    globalActiveTouchpointId = null;
    const panel = document.getElementById('slideOutPanel');
    if(panel) panel.classList.add('translate-x-full');
};

window.submitActionLog = async function() {
    if (!globalActiveTouchpointId) return;

    const commentBox = document.getElementById('log-comment');
    const statusBox = document.getElementById('log-status');
    const pendingBox = document.getElementById('log-pending');
    const pointersBox = document.getElementById('log-pointers');
    const projectSelector = document.getElementById('projectSelector');

    const payload = {
        action_type: "Manual Update",
        action_by: "Project Manager",
        comment: commentBox ? commentBox.value.trim() : '',
        new_status: (statusBox && statusBox.value !== "") ? statusBox.value : null,
        pending_with: pendingBox ? pendingBox.value : '',
        open_pointers: pointersBox ? pointersBox.value.trim() : ''
    };

    try {
        const response = await fetch(`/tasks/${globalActiveTouchpointId}/log`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            await loadData(projectSelector.value);
            const updatedIndex = globalTrackerData.findIndex(t => t.id === globalActiveTouchpointId);
            if (updatedIndex !== -1) window.openFlyout(updatedIndex);
        } else {
            alert("Failed to save update.");
        }
    } catch (error) {
        console.error("Error saving log:", error);
    }
};

window.switchPhase = function(phaseNumber) {
    // --- Hide ALL boards completely (remove every layout class, then add hidden) ---
    const phase1 = document.getElementById('phase1-board');
    const phase2 = document.getElementById('phase2-board');
    const phase3 = document.getElementById('phase3-board');

    if (phase1) {
        phase1.classList.add('hidden');
        phase1.classList.remove('block', 'flex');
    }
    if (phase2) {
        phase2.classList.add('hidden');
        phase2.classList.remove('block', 'flex');
    }
    if (phase3) {
        phase3.classList.add('hidden');
        phase3.classList.remove('block', 'flex');
    }

    const emptyState = document.getElementById('empty-state');
    if (emptyState) {
        emptyState.classList.add('hidden');
        emptyState.classList.remove('flex');
    }

    // --- Reset nav button styling ---
    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(btn => {
        btn.className = "w-10 h-10 rounded-full text-slate-400 hover:text-white hover:bg-slate-700 flex items-center justify-center transition-all nav-btn";
    });
    const activeBtn = document.getElementById(`nav-${phaseNumber}`);
    if (activeBtn) {
        activeBtn.className = "w-10 h-10 rounded-full bg-pink-500 flex items-center justify-center text-white shadow-md transition-all nav-btn";
    }

    // --- Show ONLY the chosen board ---
    if (phaseNumber === 1) {
        if (globalTrackerData && globalTrackerData.length > 0) {
            if (phase1) {
                phase1.classList.remove('hidden');
                phase1.classList.add('block');
            }
        } else {
            if (emptyState) {
                emptyState.classList.remove('hidden');
                emptyState.classList.add('flex');
            }
        }
    } else if (phaseNumber === 2) {
        if (phase2) {
            phase2.classList.remove('hidden');
            phase2.classList.add('flex');
        }

        // Reset the inner Phase 2 sub-views (in case detail view was open)
        const detailView = document.getElementById('tech-detail-view');
        const dashboardView = document.getElementById('tech-dashboard-view');
        if (detailView) { detailView.classList.add('hidden'); detailView.classList.remove('block'); }
        if (dashboardView) { dashboardView.classList.remove('hidden'); dashboardView.classList.add('block'); }

        // Clear stale data and KPI counters so previous project's rows don't flash
        window.phase2DataMap = {};
        const tbody = document.getElementById('tech-table-body');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-5 py-12 text-center text-sm font-medium text-slate-400">Loading Phase 2 data...</td></tr>';
        }
        ['tech-metric-total','tech-metric-pending','tech-metric-scheduled',
         'tech-metric-rescheduled','tech-metric-inprogress','tech-metric-delayed'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerText = '0';
        });

        // Sync currently-selected project so the API call filters correctly
        const selector = document.getElementById('projectSelector');
        if (selector && selector.value) {
            window.currentProjectName = selector.value;
        }

        // Trigger the actual data fetch (lives in phase2_technical.js)
        if (typeof populateTechTable === 'function') {
            populateTechTable();
        }
    } else if (phaseNumber === 3) {
        if (phase3) {
            phase3.classList.remove('hidden');
            phase3.classList.add('flex');
        }
    }
};

window.toggleAccordion = function(sectionId) {
    const sections = ['acc-pointers', 'acc-remarks'];

    sections.forEach(id => {
        const el = document.getElementById(id);
        const icon = document.getElementById(`icon-${id}`);

        if (id === sectionId) {
            if (el && el.classList.contains('hidden')) {
                el.classList.remove('hidden');
                if(icon) icon.classList.add('rotate-180');
            } else if (el) {
                el.classList.add('hidden');
                if(icon) icon.classList.remove('rotate-180');
            }
        } else {
            if(el) el.classList.add('hidden');
            if(icon) icon.classList.remove('rotate-180');
        }
    });
};

window.sendOnDemandReport = async function() {
    const btn = document.getElementById('btn-send-report');
    const statusText = document.getElementById('lastUpdatedText');
    
    // 1. Change UI to Loading State
    const originalHtml = btn.innerHTML;
    btn.innerHTML = `<svg class="animate-spin w-4 h-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Sending...`;
    btn.disabled = true;
    btn.classList.add('opacity-75', 'cursor-not-allowed');
    if(statusText) statusText.innerText = "Dispatching Email...";

    try {
        // 2. Call the backend route we already made in main.py
        const response = await fetch('/test-daily-email');
        
        if (response.ok) {
            if(statusText) statusText.innerText = "Email Sent Successfully!";
            // Flash a success confirmation on the button
            btn.classList.replace('text-indigo-600', 'text-emerald-600');
            btn.classList.replace('bg-indigo-50', 'bg-emerald-50');
            btn.innerHTML = `<svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> Sent!`;
        } else {
            alert("Failed to send report. Check terminal logs.");
            if(statusText) statusText.innerText = "Send Failed";
        }
    } catch (error) {
        console.error("Email Error:", error);
        alert("Could not connect to server to send email.");
    } finally {
        // 3. Reset the UI back to normal after 3 seconds
        setTimeout(() => {
            btn.innerHTML = originalHtml;
            btn.disabled = false;
            btn.classList.remove('opacity-75', 'cursor-not-allowed', 'text-emerald-600', 'bg-emerald-50');
            btn.classList.add('text-indigo-600', 'bg-indigo-50');
            if(statusText) statusText.innerText = "Ready";
        }, 3000);
    }
};
// --- EXPORT REPORT ENGINE ---
window.downloadReport = function() {
    const projectSelector = document.getElementById('projectSelector');
    if (!projectSelector || !projectSelector.value) {
        alert("Please select a project first!");
        return;
    }
    
    // This tells the browser to navigate to the download link, 
    // which triggers the "Save As..." dialog without leaving the page!
    window.open(`/tasks/${projectSelector.value}/export`, '_blank');
};

window.downloadMigrationTemplate = function() {
    const projectSelector = document.getElementById('projectSelector');
    if (!projectSelector || !projectSelector.value) {
        alert("Please select a project first!");
        return;
    }
    window.open(`/admin/migration-template/${projectSelector.value}`, '_blank');
};