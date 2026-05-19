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
        <div class="mt-8 pt-5 flex justify-end" style="border-top: 1px solid var(--border-subtle);">
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

// Enter/Escape key handling for modal
document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('new-project-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    if (e.key === 'Enter') submitNewProject();
    if (e.key === 'Escape') closeNewProjectModal();
});
