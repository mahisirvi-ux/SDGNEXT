// ==========================================
// Landing Page — js/landing.js
// ==========================================

let landingProjects = [];

document.addEventListener('DOMContentLoaded', () => {
    loadLanding();
});

async function loadLanding() {
    try {
        const [summaryRes, projectsRes] = await Promise.all([
            fetch('/api/landing/summary'),
            fetch('/projects')
        ]);
        const summary = await summaryRes.json();
        const projects = await projectsRes.json();

        landingProjects = projects;
        renderKpis(summary);
        renderProjectList(projects, '');

        // Show/hide empty state
        if (projects.length === 0) {
            document.getElementById('project-list-section').classList.add('hidden');
            document.getElementById('kpi-operational').classList.add('hidden');
            document.getElementById('empty-state').classList.remove('hidden');
        }
    } catch (err) {
        console.error("Landing load failed:", err);
        document.getElementById('project-cards').innerHTML =
            '<p class="text-sm text-red-400 p-4">Failed to load. <button onclick="loadLanding()" class="underline text-indigo-500">Retry</button></p>';
    }
}

function renderKpis(summary) {
    const cp = summary.cross_project || {};
    const po = summary.projects_overview || {};

    setText('kpi-open-fus', cp.open_followups_total);
    setText('kpi-overdue', cp.overdue_followups_total);
    setText('kpi-due-week', cp.due_this_week_total);
    setText('kpi-closed-7d', cp.closed_last_7_days_total);
    setText('kpi-mom-drafts', cp.mom_active_drafts_total);

    setText('kpi-total-projects', po.total_projects);
    setText('kpi-added-month', po.created_this_month);
    setText('kpi-touchpoints', po.touchpoints_total);
    setText('kpi-phase1-done', po.phase1_signed_off_total);
    setText('kpi-phase2-done', po.phase2_completed_total);
}

function renderProjectList(projects, searchTerm) {
    const container = document.getElementById('project-cards');
    const filtered = searchTerm
        ? projects.filter(p => p.project_name.toLowerCase().includes(searchTerm.toLowerCase()))
        : projects;

    if (filtered.length === 0 && searchTerm) {
        container.innerHTML = `<div class="p-6 text-center border border-dashed border-slate-200 rounded-xl">
            <p class="text-sm text-slate-400">No projects match '<strong>${escHtml(searchTerm)}</strong>'.</p>
        </div>`;
        return;
    }

    if (filtered.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = filtered.map(p => {
        const overduePart = p.overdue_followups > 0
            ? ` · <span class="text-red-600 font-medium">${p.overdue_followups} overdue</span>`
            : '';

        let bodyRow1;
        if (p.touchpoint_count === 0) {
            bodyRow1 = '<span class="italic text-slate-400">No touchpoints yet — open to upload your first IDR CSV</span>';
        } else {
            bodyRow1 = `${p.touchpoint_count} touchpoints · ${p.open_followups} open follow-ups${overduePart}`;
        }

        let bodyRow2 = '';
        if (p.last_activity_at) {
            bodyRow2 = `<p class="text-[11px] text-slate-400 mt-1">Last activity: ${formatRelative(p.last_activity_at)}</p>`;
        } else if (p.created_at) {
            bodyRow2 = `<p class="text-[11px] text-slate-400 mt-1">Created: ${formatDate(p.created_at)}</p>`;
        }

        return `<a href="/project?id=${p.id}" class="block bg-white rounded-xl border border-slate-200 shadow-sm p-4 hover:border-slate-300 hover:shadow-md transition-all group">
            <div class="flex items-center justify-between">
                <h3 class="text-sm font-bold text-[#1a233a]">${escHtml(p.project_name)}</h3>
                <span class="text-[10px] font-bold text-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity">Open →</span>
            </div>
            <p class="text-xs text-slate-500 mt-1.5">${bodyRow1}</p>
            ${bodyRow2}
        </a>`;
    }).join('');
}

// ==========================================
// SEARCH
// ==========================================

function applySearch(value) {
    const clearBtn = document.getElementById('search-clear');
    clearBtn.classList.toggle('hidden', !value);
    renderProjectList(landingProjects, value);
}

function clearSearch() {
    const input = document.getElementById('project-search');
    input.value = '';
    document.getElementById('search-clear').classList.add('hidden');
    renderProjectList(landingProjects, '');
}

// ==========================================
// NEW PROJECT MODAL
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
            // Reload to pick up new project
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

// ==========================================
// HELPERS
// ==========================================

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? 0;
}

function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatRelative(isoStr) {
    if (!isoStr) return '';
    const date = new Date(isoStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    return formatDate(isoStr);
}

function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

// Enter key in modal input
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !document.getElementById('new-project-modal').classList.contains('hidden')) {
        submitNewProject();
    }
    if (e.key === 'Escape' && !document.getElementById('new-project-modal').classList.contains('hidden')) {
        closeNewProjectModal();
    }
});
