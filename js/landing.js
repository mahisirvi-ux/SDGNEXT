// ==========================================
// Landing Page — js/landing.js
// Analytical sparkline cards + inline drilldown
// Executive Polish Edition
// ==========================================

let landingState = {
    projects: [],
    expandedProjectId: null,
    drilldownCache: {}
};

document.addEventListener('DOMContentLoaded', () => {
    loadLanding();
});

// ==========================================
// DATA LOADING
// ==========================================

async function loadLanding() {
    try {
        const res = await fetch('/api/landing/project-sparklines');
        if (!res.ok) throw new Error('Fetch failed');
        const data = await res.json();
        landingState.projects = data.projects || [];
        renderPage();
    } catch (err) {
        console.error('Landing load failed:', err);
        renderError(err);
    }
}

function renderPage() {
    const grid = document.getElementById('project-cards-grid');
    const empty = document.getElementById('empty-state');
    if (!grid) return;

    if (landingState.projects.length === 0) {
        grid.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    grid.classList.remove('hidden');
    grid.innerHTML = landingState.projects.map(renderCard).join('');
}

function renderError(err) {
    const grid = document.getElementById('project-cards-grid');
    if (!grid) return;
    grid.innerHTML = `<div class="col-span-full text-center py-12">
        <p class="text-sm" style="color: var(--text-secondary);">Failed to load projects.</p>
        <button onclick="loadLanding()" class="mt-3 text-xs font-semibold px-4 py-2 rounded-lg" style="background: var(--shell); color: white;">Retry</button>
    </div>`;
}

// ==========================================
// CARD RENDERING
// ==========================================

function renderCard(p) {
    const hasData = p.data_points > 0;
    const isExpanded = landingState.expandedProjectId === p.id;

    const borderStyle = isExpanded
        ? 'border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft);'
        : 'border-color: var(--border-default);';

    const badge = hasData
        ? `<span class="text-[10px] uppercase tracking-wider tabular-nums" style="color: var(--accent); background: var(--accent-faint); padding: 2px 8px; border-radius: 3px;">Active</span>`
        : `<span class="text-[10px] uppercase tracking-wider" style="color: var(--text-meta);">No data yet</span>`;

    return `<div class="project-card bg-white rounded-xl border p-6 cursor-pointer"
        style="${borderStyle}"
        data-project-id="${p.id}"
        onclick="expandProject(${p.id})">
        <div class="flex items-center justify-between mb-5">
            <h3 class="text-base font-semibold" style="color: var(--text-primary);">${escapeHtml(p.project_name)}</h3>
            ${badge}
        </div>
        <div class="grid grid-cols-2 gap-x-6 gap-y-5">
            ${renderMetricCell('Open Follow-ups', p.current.open_followups, p.sparklines.open_followups, p.trend.open_followups, false)}
            ${renderMetricCell('Overdue', p.current.overdue_followups, p.sparklines.overdue_followups, p.trend.overdue_followups, p.current.overdue_followups > 0)}
            ${renderMetricCell('Active Touchpoints', p.current.touchpoints_active, p.sparklines.touchpoints_active, p.trend.touchpoints_active, false)}
            ${renderMetricCell('Workshops Completed', p.current.workshops_completed, p.sparklines.workshops_completed, p.trend.workshops_completed, false)}
        </div>
        <div class="mt-5 pt-4 flex items-center justify-between text-[10px]" style="border-top: 1px solid var(--border-subtle); color: var(--text-meta);">
            <span class="tabular-nums">${p.touchpoint_count} touchpoint${p.touchpoint_count !== 1 ? 's' : ''}</span>
            <span>${isExpanded ? 'Click again to collapse' : 'Click to expand'}</span>
        </div>
    </div>`;
}

// ==========================================
// METRIC CELL (weight-by-meaning)
// ==========================================

function renderMetricCell(label, value, sparkData, trend, isUrgent) {
    const numberWeight = isUrgent ? 'font-semibold' : 'font-light';
    const numberColor = isUrgent ? 'color: var(--warn);' : 'color: var(--text-display);';

    let arrow, arrowColor;
    if (trend === 'up') {
        arrow = '\u2191';
        arrowColor = isUrgent ? 'var(--warn)' : 'var(--text-meta)';
    } else if (trend === 'down') {
        arrow = '\u2193';
        arrowColor = isUrgent ? '#10b981' : 'var(--text-meta)';
    } else {
        arrow = '\u00B7';
        arrowColor = 'var(--text-quiet)';
    }

    return `<div>
        <p class="text-[10px] uppercase tracking-wider mb-2" style="color: var(--text-secondary); font-weight: 700; letter-spacing: 0.06em;">${label}</p>
        <div class="flex items-baseline gap-2">
            <span class="text-3xl tabular-nums ${numberWeight}" style="${numberColor}">${formatNumber(value)}</span>
            <span class="text-sm tabular-nums" style="color: ${arrowColor}; font-weight: 500;">${arrow}</span>
        </div>
        <div class="mt-2">${renderSparkline(sparkData, isUrgent)}</div>
    </div>`;
}

// ==========================================
// SVG SPARKLINE (gradient + baseline)
// ==========================================

function renderSparkline(values, isUrgent) {
    if (!values || values.length === 0) {
        return `<div class="h-6 flex items-end"><div style="height:1px;width:100%;background:var(--border-subtle);"></div></div>`;
    }

    const width = 100;
    const height = 24;
    const padding = 2;
    const id = 'sg-' + Math.random().toString(36).slice(2, 8);

    // Single data point: dot + baseline
    if (values.length === 1) {
        const color = isUrgent ? '#d97706' : '#0d9488';
        return `<svg width="${width}" height="${height}" class="block" style="overflow:visible;">
            <line x1="0" y1="${height - padding}" x2="${width}" y2="${height - padding}" stroke="var(--border-subtle)" stroke-width="1"/>
            <circle cx="${width / 2}" cy="${height / 2}" r="2" fill="${color}"/>
        </svg>`;
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const stepX = (width - 2 * padding) / (values.length - 1);

    const coords = values.map((v, i) => {
        const x = padding + i * stepX;
        const y = height - padding - ((v - min) / range) * (height - 2 * padding);
        return [x, y];
    });

    const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    const lastPt = coords[coords.length - 1];

    const stroke = isUrgent ? '#d97706' : `url(#${id})`;
    const gradientDef = isUrgent ? '' : `<defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#cbd5e1" stop-opacity="0.6"/><stop offset="100%" stop-color="#0d9488" stop-opacity="0.95"/></linearGradient></defs>`;

    return `<svg width="${width}" height="${height}" class="block" style="overflow:visible;">
        ${gradientDef}
        <line x1="0" y1="${height - padding}" x2="${width}" y2="${height - padding}" stroke="var(--border-subtle)" stroke-width="1"/>
        <polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="${lastPt[0].toFixed(1)}" cy="${lastPt[1].toFixed(1)}" r="1.8" fill="${isUrgent ? '#d97706' : '#0d9488'}"/>
    </svg>`;
}

// ==========================================
// DRILLDOWN LIFECYCLE
// ==========================================

async function expandProject(projectId) {
    // Toggle: same card collapses
    if (landingState.expandedProjectId === projectId) {
        landingState.expandedProjectId = null;
        document.getElementById('project-drilldown').classList.add('hidden');
        renderPage();
        return;
    }

    landingState.expandedProjectId = projectId;
    renderPage();

    const panel = document.getElementById('project-drilldown');
    panel.classList.remove('hidden');
    panel.innerHTML = renderDrilldownLoading();

    // Use cache if available
    let data = landingState.drilldownCache[projectId];
    if (!data) {
        try {
            const resp = await fetch(`/api/landing/projects/${projectId}/drilldown`);
            if (!resp.ok) throw new Error('Drilldown fetch failed');
            data = await resp.json();
            landingState.drilldownCache[projectId] = data;
        } catch (err) {
            panel.innerHTML = renderDrilldownError(projectId);
            return;
        }
    }

    panel.innerHTML = renderDrilldown(projectId, data);
    // Animation
    if (panel.firstElementChild) {
        panel.firstElementChild.classList.add('drilldown-enter');
    }
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeDrilldown() {
    landingState.expandedProjectId = null;
    document.getElementById('project-drilldown').classList.add('hidden');
    document.getElementById('project-drilldown').innerHTML = '';
    renderPage();
}

// ==========================================
// DRILLDOWN RENDERERS
// ==========================================

function renderDrilldown(projectId, d) {
    const hasDepts = (d.admin.department_count || 0) > 0;
    const hasTeam  = (d.admin.team_member_count || 0) > 0;

    // Step states
    const step1Done = hasDepts;
    const step2Done = hasTeam;
    // step3 (touchpoints) is always available once the other two are done — but upload is always enabled once project exists

        // Unique dropdown key per step per project
        const stepCard = (title, dropKey, inputId, locked, done, manualFn) => {
            const doneBadge = done
                ? `<span class="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                     <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>Done
                   </span>`
                : (locked
                    ? `<span class="text-[10px] font-bold text-slate-400 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">Locked</span>`
                    : `<span class="text-[10px] font-bold text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">Pending</span>`);

            const wrapperBg  = done    ? 'border-emerald-200 bg-emerald-50'
                             : locked  ? 'border-slate-200 bg-slate-100 opacity-50'
                             :           'bg-[#1a233a] border-[#1a233a]';
            const textColor  = done    ? 'text-emerald-700'
                             : locked  ? 'text-slate-400'
                             :           'text-white';
            const caretColor = done    ? 'text-emerald-500'
                             : locked  ? 'text-slate-300'
                             :           'text-white/70';

            const disabledPointer = locked ? 'pointer-events-none' : '';

            return `
            <div class="relative ${disabledPointer}" id="dd-wrap-${dropKey}">
                <!-- Main button row -->
                <div class="w-full flex items-center rounded-lg border overflow-hidden ${wrapperBg}">
                    <!-- Label area -->
                    <div class="flex-1 flex items-center justify-between gap-2 px-4 py-3">
                        <span class="text-sm font-semibold ${textColor}">${title}</span>
                        ${doneBadge}
                    </div>
                    <!-- Divider -->
                    <div class="w-px self-stretch ${done ? 'bg-emerald-200' : (locked ? 'bg-slate-200' : 'bg-white/20')}"></div>
                    <!-- Caret toggle -->
                    <button type="button"
                        onclick="toggleStepDropdown('dd-menu-${dropKey}', 'dd-caret-${dropKey}')"
                        class="px-3 py-3 flex items-center justify-center transition-colors ${done ? 'hover:bg-emerald-100' : 'hover:bg-white/10'}"
                        title="More options">
                        <svg id="dd-caret-${dropKey}" class="w-4 h-4 transition-transform ${caretColor}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                        </svg>
                    </button>
                </div>

                <!-- Dropdown menu -->
                <div id="dd-menu-${dropKey}" class="hidden absolute left-0 right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-30 overflow-hidden">
                    <!-- Upload CSV -->
                    <button type="button"
                        onclick="document.getElementById('${inputId}').click(); toggleStepDropdown('dd-menu-${dropKey}', 'dd-caret-${dropKey}')"
                        class="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-50 transition-colors border-b border-slate-100">
                        <div class="w-7 h-7 rounded-md bg-[#1a233a] flex items-center justify-center flex-shrink-0">
                            <svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                        </div>
                        <span class="text-xs font-semibold text-[#1a233a]">Upload CSV</span>
                    </button>
                    <!-- Add Manually -->
                    <button type="button"
                        onclick="${manualFn}; toggleStepDropdown('dd-menu-${dropKey}', 'dd-caret-${dropKey}')"
                        class="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-50 transition-colors">
                        <div class="w-7 h-7 rounded-md bg-slate-100 flex items-center justify-center flex-shrink-0">
                            <svg class="w-3.5 h-3.5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                        </div>
                        <span class="text-xs font-semibold text-slate-700">Add Manually</span>
                    </button>
                </div>

                <!-- Hidden file input -->
                <input type="file" id="${inputId}" class="hidden" accept=".csv"
                    onchange="handleDrilldownUpload(event, ${projectId}, '${dropKey.split('-')[0]}')"/>
            </div>`;
        };

    return `<div class="bg-white rounded-xl border p-7 relative" style="border-color: var(--border-default); box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
        <button onclick="closeDrilldown()" class="absolute top-5 right-5" style="color: var(--text-meta);" aria-label="Close drilldown">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
        <h3 class="text-lg font-semibold mb-1" style="color: var(--text-primary);">${escapeHtml(d.admin.project_name)}</h3>
        <p class="text-xs mb-6" style="color: var(--text-secondary);">Project drilldown</p>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            ${renderAdminSection(d.admin)}
            ${renderHealthSection(d.health)}
            ${renderActivitySection(d.recent_activity)}
        </div>

                <div class="mt-8 pt-6" style="border-top: 1px solid var(--border-subtle);">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
                ${stepCard(
                    'Departments',
                    'departments-' + projectId,
                    'dd-depts-input-' + projectId,
                    false,
                    step1Done,
                    `openManualModal('departments', ${projectId})`
                )}
                ${stepCard(
                    'Team Members',
                    'team-' + projectId,
                    'dd-team-input-' + projectId,
                    !step1Done,
                    step2Done,
                    `openManualModal('team', ${projectId})`
                )}
                ${stepCard(
                    'Touchpoints',
                    'touchpoints-' + projectId,
                    'dd-tp-input-' + projectId,
                    !step2Done,
                    false,
                    `openManualModal('touchpoints', ${projectId})`
                )}
            </div>

            <!-- Upload status message -->
            <div id="dd-upload-status-${projectId}" class="hidden mt-3 text-[11px] font-medium px-3 py-2 rounded-lg border"></div>
        </div>

        <div class="mt-6 flex justify-end">
            <a href="/project?id=${projectId}" class="text-xs font-semibold px-5 py-2.5 rounded-lg shadow-sm inline-flex items-center gap-2 transition-all" style="background: var(--shell); color: white;">
                Open Project
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
            </a>
        </div>
    </div>`;
}

function renderAdminSection(a) {
    return renderDefSection('Administrative', [
        ['Created', a.created_at ? fmtDate(a.created_at) : '\u2014'],
        ['Touchpoints', formatNumber(a.touchpoint_count)],
        ['Departments', formatNumber(a.department_count)],
        ['Team members', formatNumber(a.team_member_count)]
    ]);
}

function renderHealthSection(h) {
    const overdueStyle = h.overdue_followups > 0 ? 'color: var(--warn); font-weight: 600;' : '';
    return renderDefSection('Health snapshot', [
        ['Open follow-ups', formatNumber(h.open_followups), ''],
        ['Overdue', formatNumber(h.overdue_followups), overdueStyle],
        ['Due this week', formatNumber(h.due_this_week), ''],
        ['Last MoM', h.last_mom_date ? `${fmtDate(h.last_mom_date)} (${h.last_mom_age_days}d)` : 'Never', ''],
        ['Workshops this week', formatNumber(h.workshops_this_week), ''],
        ['Workshops done', formatNumber(h.workshops_completed_total), '']
    ]);
}

function renderDefSection(title, rows) {
    const rowsHtml = rows.map(([k, v, style]) => `
        <div class="flex justify-between py-2" style="border-bottom: 1px solid var(--border-subtle);">
            <dt class="text-xs" style="color: var(--text-secondary);">${k}</dt>
            <dd class="text-xs tabular-nums" style="color: var(--text-body); font-weight: 500; ${style || ''}">${v}</dd>
        </div>
    `).join('');

    return `<div>
        <h4 class="text-[10px] uppercase tracking-wider mb-4" style="color: var(--text-secondary); font-weight: 700; letter-spacing: 0.08em;">${title}</h4>
        <dl>${rowsHtml}</dl>
    </div>`;
}

function renderActivitySection(activities) {
    const title = `<h4 class="text-[10px] uppercase tracking-wider mb-4" style="color: var(--text-secondary); font-weight: 700; letter-spacing: 0.08em;">Recent Activity</h4>`;

    if (!activities || activities.length === 0) {
        return `<div>${title}<p class="text-xs italic" style="color: var(--text-meta);">No activity yet</p></div>`;
    }

    const items = activities.map((a, i) => `
        <div class="relative pl-5" style="${i < activities.length - 1 ? 'padding-bottom: 14px;' : ''}">
            ${i < activities.length - 1 ? `<div style="position:absolute;left:4px;top:8px;bottom:0;width:1px;background:var(--border-default);"></div>` : ''}
            <div style="position:absolute;left:0;top:4px;width:9px;height:9px;border-radius:50%;background:white;border:1.5px solid var(--accent);"></div>
            <div class="text-xs" style="color: var(--text-body); font-weight: 500; line-height: 1.5;">${formatActionLabel(a)}</div>
            <div class="text-[11px] mt-0.5" style="color: var(--text-secondary);">${escapeHtml(a.touchpoint_name || '')}</div>
            <div class="text-[10px] mt-0.5 tabular-nums" style="color: var(--text-meta);">${escapeHtml(a.relative_time)}</div>
        </div>
    `).join('');

    return `<div>${title}<div>${items}</div></div>`;
}

function renderDrilldownLoading() {
    return `<div class="bg-white rounded-xl border p-7" style="border-color: var(--border-default);">
        <div class="skeleton" style="height:22px;width:200px;margin-bottom:8px;"></div>
        <div class="skeleton" style="height:14px;width:120px;margin-bottom:24px;"></div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="space-y-3">${Array(4).fill('<div class="skeleton" style="height:14px;"></div>').join('')}</div>
            <div class="space-y-3">${Array(5).fill('<div class="skeleton" style="height:14px;"></div>').join('')}</div>
            <div class="space-y-3">${Array(4).fill('<div class="skeleton" style="height:14px;"></div>').join('')}</div>
        </div>
    </div>`;
}

function renderDrilldownError(projectId) {
    return `<div class="bg-white rounded-xl border p-7 text-center" style="border-color: var(--border-default);">
        <p class="text-sm" style="color: var(--text-secondary);">Could not load project details.</p>
        <button onclick="expandProject(${projectId})" class="mt-3 text-xs font-semibold px-4 py-2 rounded-lg" style="background: var(--shell); color: white;">Retry</button>
    </div>`;
}

// ==========================================
// HELPERS
// ==========================================

function formatActionLabel(a) {
    const map = {
        'DISCUSSION': 'Discussion added',
        'POINTER': 'Open pointer raised',
        'STATUS_CHANGE': 'Status changed',
        'Manual Update': 'Manual edit',
        'MOM_SENT': 'MoM emailed',
        'MOM_NUDGE_SENT': 'MoM nudge sent',
        'FOLLOWUP_CLOSED': 'Follow-up closed',
        'FOLLOWUP_REOPENED': 'Follow-up reopened',
        'WORKSHOP_INVITE_SENT': 'Workshop invite sent'
    };
    return map[a.action_type] || a.action_type;
}

function formatNumber(n) {
    if (n === null || n === undefined) return '\u2014';
    if (n === 0) return '0';
    return n.toLocaleString('en-US');
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(isoStr) {
    if (!isoStr) return '\u2014';
    try {
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return isoStr;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch { return '\u2014'; }
}

// ==========================================
// DRILLDOWN UPLOAD HANDLER
// ==========================================

window.handleDrilldownUpload = async function(event, projectId, uploadType) {
    const file = event.target.files[0];
    if (!file) return;
    // Reset input so same file can be re-selected if needed
    event.target.value = '';

    // Find the project name from the landing state
    const project = landingState.projects.find(p => p.id === projectId);
    const projectName = project ? project.project_name : null;

    const statusEl = document.getElementById(`dd-upload-status-${projectId}`);

    const setStatus = (msg, type) => {
        if (!statusEl) return;
        statusEl.classList.remove('hidden', 'text-emerald-700', 'bg-emerald-50', 'border-emerald-200',
                                            'text-red-700',     'bg-red-50',     'border-red-200',
                                            'text-slate-600',   'bg-slate-50',   'border-slate-200');
        if (type === 'success') {
            statusEl.classList.add('text-emerald-700', 'bg-emerald-50', 'border-emerald-200');
        } else if (type === 'error') {
            statusEl.classList.add('text-red-700', 'bg-red-50', 'border-red-200');
        } else {
            statusEl.classList.add('text-slate-600', 'bg-slate-50', 'border-slate-200');
        }
        statusEl.textContent = msg;
        statusEl.classList.remove('hidden');
    };

    if (!projectName) {
        setStatus('Could not resolve project name. Please refresh and try again.', 'error');
        return;
    }

    // Map uploadType to endpoint URL and label
    const uploadMap = {
        departments: { url: `/upload-departments/${projectName}`,  label: 'Departments' },
        team:        { url: `/upload-team-members/${projectName}`, label: 'Team Members' },
        touchpoints: { url: `/upload-csv/${projectName}`,          label: 'Touchpoints' }
    };

    const { url, label } = uploadMap[uploadType];
    setStatus(`Uploading ${label}...`, 'info');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(url, { method: 'POST', body: formData });
        const result   = await response.json().catch(() => ({}));

        if (response.ok) {
            let summary = result.message || `${label} uploaded successfully.`;
            if (result.skipped_rows && Array.isArray(result.skipped_rows) && result.skipped_rows.length) {
                summary += ` (${result.skipped_rows.length} row(s) skipped)`;
            }
            setStatus(`✓ ${summary}`, 'success');

            // Bust the drilldown cache so re-opening reflects new counts
            delete landingState.drilldownCache[projectId];

            // Refresh the landing data so sparkline counts update
            setTimeout(() => {
                loadLanding();
                // Re-expand the same project so the wizard re-renders with updated state
                setTimeout(() => expandProject(projectId), 400);
            }, 800);
        } else {
            const errMsg = result.detail || result.message || 'Upload failed — check CSV format.';
            setStatus(`✗ ${errMsg}`, 'error');
        }
    } catch (err) {
        console.error(`${label} upload error:`, err);
        setStatus('Network error. Please try again.', 'error');
    }
};

// ==========================================
// STEP DROPDOWN TOGGLE
// ==========================================

window.toggleStepDropdown = function(menuId, caretId) {
    document.querySelectorAll('[id^="dd-menu-"]').forEach(function(el) {
        if (el.id !== menuId) {
            el.classList.add('hidden');
            var c = document.getElementById(el.id.replace('dd-menu-', 'dd-caret-'));
            if (c) c.classList.remove('rotate-180');
        }
    });
    var menu  = document.getElementById(menuId);
    var caret = document.getElementById(caretId);
    if (menu)  menu.classList.toggle('hidden');
    if (caret) caret.classList.toggle('rotate-180');
};

document.addEventListener('click', function(e) {
    if (!e.target.closest('[id^="dd-wrap-"]')) {
        document.querySelectorAll('[id^="dd-menu-"]').forEach(function(el) {
            el.classList.add('hidden');
        });
        document.querySelectorAll('[id^="dd-caret-"]').forEach(function(el) {
            el.classList.remove('rotate-180');
        });
    }
});

// ==========================================
// MANUAL ENTRY MODAL
// ==========================================

window.openManualModal = async function(type, projectId) {
    var modal    = document.getElementById('manual-entry-modal');
    var title    = document.getElementById('manual-modal-title');
    var body     = document.getElementById('manual-modal-body');
    var projId   = document.getElementById('manual-modal-project-id');
    var projType = document.getElementById('manual-modal-type');
    if (!modal) return;

    projId.value   = projectId;
    projType.value = type;

    // Fetch dept options (for team modal) AND team member options (for touchpoints modal)
    var deptOptions   = [];
    var memberOptions = [];

    if (type === 'team') {
        try {
            var r = await fetch('/api/projects/' + projectId + '/departments');
            if (r.ok) {
                var depts = await r.json();
                deptOptions = depts.map(function(d) {
                    return { value: d.dept_id, label: d.dept_id + ' \u2014 ' + d.name };
                });
            }
        } catch(e) {}
    }

    if (type === 'touchpoints') {
        try {
            var r2 = await fetch('/api/projects/' + projectId + '/team-members');
            if (r2.ok) {
                var members = await r2.json();
                memberOptions = members.map(function(m) {
                    return { value: m.full_name, label: m.full_name + ' (' + m.dept_id + ')' };
                });
            }
        } catch(e) {}
    }

    var configs = {
        departments: {
            title: 'Add Department',
            fields: [
                { id: 'f-dept-id',    label: 'Dept ID',  placeholder: 'e.g. CBS',          required: true  },
                { id: 'f-dept-name',  label: 'Name',     placeholder: 'e.g. Core Banking', required: true  },
                { id: 'f-dept-email', label: 'Email',    placeholder: 'dept@company.com',  required: false },
                { id: 'f-dept-crm',   label: 'Is CRM',   placeholder: '',                  required: false, type: 'select', options: ['Yes','No'] }
            ]
        },
        team: {
            title: 'Add Team Member',
            fields: [
                { id: 'f-tm-name',  label: 'Full Name',    placeholder: 'e.g. John Smith',  required: true  },
                { id: 'f-tm-email', label: 'Email',        placeholder: 'john@company.com', required: true  },
                { id: 'f-tm-phone', label: 'Mobile Phone', placeholder: '+91-9999999999',   required: false },
                { id: 'f-tm-dept',  label: 'Dept ID',      placeholder: '',                 required: true,  type: 'dept-select' },
                { id: 'f-tm-crm',   label: 'Is CRM User',  placeholder: '',                 required: false, type: 'select', options: ['Yes','No'] }
            ]
        },
        touchpoints: {
            title: 'Add Touchpoint',
            fields: [
                { id: 'f-tp-name',       label: 'Integration Touchpoint',         placeholder: 'e.g. Customer CIF Creation',  required: true,  col: 'full' },
                { id: 'f-tp-module',     label: 'Module / Journey',                placeholder: 'e.g. Assets',                required: false },
                { id: 'f-tp-mod-owner',  label: 'Module Owner (Functional)',       placeholder: '',                            required: false, type: 'member-select' },
                { id: 'f-tp-tech-owner', label: 'Technical Owner (CRM)',           placeholder: '',                            required: false, type: 'member-select' },
                { id: 'f-tp-owner',      label: 'Business Dept Owner',             placeholder: '',                            required: false, type: 'member-select' },
                { id: 'f-tp-flow',       label: 'Business Flow / Objective',       placeholder: 'Describe the business flow',  required: false, type: 'textarea' },
                { id: 'f-tp-direction',  label: 'Integration Direction',           placeholder: '',                            required: false, type: 'select', options: ['Inbound','Outbound','Bidirectional'] },
                { id: 'f-tp-source',     label: 'Source System',                   placeholder: 'e.g. Core Banking',           required: false },
                { id: 'f-tp-target',     label: 'Target System',                   placeholder: 'e.g. CRM',                    required: false },
                { id: 'f-tp-trigger',    label: 'Trigger Mechanism',               placeholder: 'e.g. On save / Batch / API',  required: false },
                { id: 'f-tp-ux',         label: 'UX Expectation',                  placeholder: 'e.g. Real-time / Async',      required: false },
                { id: 'f-tp-fallback',   label: 'Business Fallback',               placeholder: 'Fallback if integration fails',required: false, type: 'textarea' },
                { id: 'f-tp-remarks',    label: 'IDR Remarks / Notes',             placeholder: 'Any notes',                   required: false, type: 'textarea' },
                { id: 'f-tp-status',     label: 'IDR Status',                      placeholder: '',                            required: false, type: 'select', options: ['Pending','In Progress','Signed-Off','On Hold'] },
                { id: 'f-tp-inputs',     label: 'Inputs',                          placeholder: 'Input fields / data',         required: false, type: 'textarea' },
                { id: 'f-tp-output',     label: 'Expected Output',                 placeholder: 'Output / response',           required: false, type: 'textarea' },
                { id: 'f-tp-dept',       label: 'Business Department',             placeholder: 'e.g. Retail Banking',         required: false },
                { id: 'f-tp-signoff',    label: 'IDR SignOff Date',                placeholder: 'YYYY-MM-DD',                  required: false },
                { id: 'f-tp-pending',    label: 'Pending With',                    placeholder: '',                            required: false, type: 'member-select' },
                { id: 'f-tp-pointers',   label: 'Open Pointers',                   placeholder: 'Any open items',              required: false, type: 'textarea' },
                { id: 'f-tp-inttype',    label: 'Integration Type',                placeholder: '',                            required: false, type: 'select', options: ['API','Database','Batch','File Transfer'] },
                { id: 'f-tp-start',      label: 'Start Time',                      placeholder: 'YYYY-MM-DD HH:MM',            required: false },
                { id: 'f-tp-end',        label: 'End Time',                        placeholder: 'YYYY-MM-DD HH:MM',            required: false }
            ]
        }
    };

    var cfg = configs[type];
    if (!cfg) return;
    title.textContent = cfg.title;

    // For touchpoints: 2-column grid layout
    var isTP = (type === 'touchpoints');

    // Widen the modal box for touchpoints (many fields)
    var box = document.getElementById('manual-modal-box');
    if (box) box.style.width = isTP ? '780px' : '420px';
    var wrapClass = isTP ? 'grid grid-cols-2 gap-3' : 'space-y-3';

    body.innerHTML = '<div class="' + wrapClass + '">' + cfg.fields.map(function(f) {
        var input;
        var colClass = (isTP && f.col === 'full') ? 'col-span-2' : '';

        if (f.type === 'dept-select') {
            var optHtml = '<option value="">-- select department --</option>';
            if (deptOptions.length === 0) {
                optHtml += '<option value="" disabled>No departments found</option>';
            } else {
                optHtml += deptOptions.map(function(o){ return '<option value="' + o.value + '">' + o.label + '</option>'; }).join('');
            }
            input = '<select id="' + f.id + '" class="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-200 focus:outline-none bg-white">' + optHtml + '</select>';

        } else if (f.type === 'member-select') {
            var mHtml = '<option value="">-- select member --</option>';
            if (memberOptions.length === 0) {
                mHtml += '<option value="" disabled>No team members found</option>';
            } else {
                mHtml += memberOptions.map(function(o){ return '<option value="' + o.value + '">' + o.label + '</option>'; }).join('');
            }
            input = '<select id="' + f.id + '" class="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-200 focus:outline-none bg-white">' + mHtml + '</select>';

        } else if (f.type === 'select') {
            input = '<select id="' + f.id + '" class="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-200 focus:outline-none bg-white"><option value="">-- select --</option>' + f.options.map(function(o){ return '<option value="' + o + '">' + o + '</option>'; }).join('') + '</select>';

        } else if (f.type === 'textarea') {
            input = '<textarea id="' + f.id + '" rows="2" placeholder="' + f.placeholder + '" class="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-200 focus:outline-none resize-none"></textarea>';

        } else {
            input = '<input type="text" id="' + f.id + '" placeholder="' + f.placeholder + '" class="w-full text-xs p-2.5 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-200 focus:outline-none">';
        }

        return '<div class="' + colClass + '"><label class="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">' + f.label + (f.required ? ' <span class="text-pink-500">*</span>' : '') + '</label>' + input + '</div>';
    }).join('') + '</div>';

    document.getElementById('manual-modal-error').classList.add('hidden');
    modal.classList.remove('hidden');
    setTimeout(function() {
        var first = body.querySelector('input, select, textarea');
        if (first) first.focus();
    }, 80);
};

window.closeManualModal = function() {
    document.getElementById('manual-entry-modal').classList.add('hidden');
};

window.submitManualEntry = async function() {
    var type        = document.getElementById('manual-modal-type').value;
    var projectId   = parseInt(document.getElementById('manual-modal-project-id').value);
    var errorEl     = document.getElementById('manual-modal-error');
    var project     = landingState.projects.find(function(p) { return p.id === projectId; });
    var projectName = project ? project.project_name : null;

    if (!projectName) {
        errorEl.textContent = 'Project not found.';
        errorEl.classList.remove('hidden');
        return;
    }

    var endpointMap = {
        departments: '/api/projects/' + projectId + '/departments',
        team:        '/api/projects/' + projectId + '/team-members',
        touchpoints: '/api/projects/' + projectId + '/touchpoints'
    };

    var payload = {};

    if (type === 'departments') {
        payload = {
            dept_id: (document.getElementById('f-dept-id')?.value    || '').trim(),
            name:    (document.getElementById('f-dept-name')?.value   || '').trim(),
            email:   (document.getElementById('f-dept-email')?.value  || '').trim(),
            is_crm:  (document.getElementById('f-dept-crm')?.value    || '').trim()
        };
        if (!payload.dept_id || !payload.name) {
            errorEl.textContent = 'Dept ID and Name are required.';
            errorEl.classList.remove('hidden');
            return;
        }
    } else if (type === 'team') {
        payload = {
            name:        (document.getElementById('f-tm-name')?.value  || '').trim(),
            email:       (document.getElementById('f-tm-email')?.value || '').trim(),
            phone:       (document.getElementById('f-tm-phone')?.value || '').trim(),
            dept_id:     (document.getElementById('f-tm-dept')?.value  || '').trim(),
            is_crm_user: (document.getElementById('f-tm-crm')?.value   || '').trim()
        };
        if (!payload.name || !payload.email || !payload.dept_id) {
            errorEl.textContent = 'Name, Email and Dept ID are required.';
            errorEl.classList.remove('hidden');
            return;
        }
    } else if (type === 'touchpoints') {
        payload = {
            name:                    (document.getElementById('f-tp-name')?.value       || '').trim(),
            module:                  (document.getElementById('f-tp-module')?.value     || '').trim(),
            module_owner_functional: (document.getElementById('f-tp-mod-owner')?.value  || '').trim(),
            technical_owner:         (document.getElementById('f-tp-tech-owner')?.value || '').trim(),
            owner:                   (document.getElementById('f-tp-owner')?.value      || '').trim(),
            business_flow:           (document.getElementById('f-tp-flow')?.value       || '').trim(),
            integration_direction:   (document.getElementById('f-tp-direction')?.value  || '').trim(),
            source_system:           (document.getElementById('f-tp-source')?.value     || '').trim(),
            target_system:           (document.getElementById('f-tp-target')?.value     || '').trim(),
            trigger_mechanism:       (document.getElementById('f-tp-trigger')?.value    || '').trim(),
            ux_expectation:          (document.getElementById('f-tp-ux')?.value         || '').trim(),
            business_fallback:       (document.getElementById('f-tp-fallback')?.value   || '').trim(),
            idr_remarks:             (document.getElementById('f-tp-remarks')?.value    || '').trim(),
            idr_status:              (document.getElementById('f-tp-status')?.value     || 'Pending').trim(),
            inputs:                  (document.getElementById('f-tp-inputs')?.value     || '').trim(),
            expected_output:         (document.getElementById('f-tp-output')?.value     || '').trim(),
            business_department:     (document.getElementById('f-tp-dept')?.value       || '').trim(),
            idr_signoff_date:        (document.getElementById('f-tp-signoff')?.value    || '').trim(),
            pending_with:            (document.getElementById('f-tp-pending')?.value    || '').trim(),
            open_pointers:           (document.getElementById('f-tp-pointers')?.value   || '').trim(),
            integration_type:        (document.getElementById('f-tp-inttype')?.value    || '').trim(),
            start_time:              (document.getElementById('f-tp-start')?.value      || '').trim(),
            end_time:                (document.getElementById('f-tp-end')?.value        || '').trim()
        };
        if (!payload.name) {
            errorEl.textContent = 'Touchpoint name is required.';
            errorEl.classList.remove('hidden');
            return;
        }
    }

    try {
        var res = await fetch(endpointMap[type], {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            closeManualModal();
            delete landingState.drilldownCache[projectId];
            await loadLanding();
            setTimeout(function() { expandProject(projectId); }, 300);
        } else {
            var err = await res.json().catch(function() { return {}; });
            errorEl.textContent = err.detail || err.message || 'Save failed.';
            errorEl.classList.remove('hidden');
        }
    } catch(e) {
        errorEl.textContent = 'Network error. Please try again.';
        errorEl.classList.remove('hidden');
    }
};

// ==========================================
// NEW PROJECT MODAL (preserved)
// ==========================================

function openNewProjectModal() {
    document.getElementById('new-project-name').value = '';
    document.getElementById('new-project-error').classList.add('hidden');
    document.getElementById('new-project-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('new-project-name').focus(), 100);
}

function closeNewProjectModal() {
    document.getElementById('new-project-modal').classList.add('hidden');
}

async function submitNewProject() {
    const input = document.getElementById('new-project-name');
    const name = input.value.trim();
    const errorEl = document.getElementById('new-project-error');

    if (!name) {
        errorEl.textContent = 'Project name is required.';
        errorEl.classList.remove('hidden');
        input.focus();
        return;
    }

    try {
        const res = await fetch('/projects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project_name: name})
        });

        if (res.status === 201 || res.ok) {
            closeNewProjectModal();
            landingState.drilldownCache = {};
            loadLanding();
        } else {
            const err = await res.json();
            errorEl.textContent = err.detail || 'Failed to create project.';
            errorEl.classList.remove('hidden');
            input.focus();
        }
    } catch (err) {
        errorEl.textContent = 'Network error.';
        errorEl.classList.remove('hidden');
    }
}

document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('new-project-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    if (e.key === 'Enter') submitNewProject();
    if (e.key === 'Escape') closeNewProjectModal();
});
