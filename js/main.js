import { initializeSidebar } from './uiController.js';
import { renderCharts } from './chartManager.js';

let currentData = [];

document.addEventListener('DOMContentLoaded', () => {
    initializeSidebar();

    const fileInput = document.getElementById('csvFileInput');
    const projectSelector = document.getElementById('projectSelector');
    const lastUpdatedText = document.getElementById('lastUpdatedText');

    // Load existing data
    loadDataForProject(projectSelector.value);

    projectSelector.addEventListener('change', (e) => loadDataForProject(e.target.value));

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        Papa.parse(file, {
            header: true,
            skipEmptyLines: true,
            complete: function(results) {
                currentData = results.data;
                const activeProject = projectSelector.value;
                
                // Save to browser memory
                localStorage.setItem(`trackerData_${activeProject}`, JSON.stringify(currentData));
                localStorage.setItem(`trackerFileName_${activeProject}`, file.name);
                
                lastUpdatedText.innerText = `Loaded: ${file.name}`;
                updateDashboard();
                fileInput.value = '';
            }
        });
    });
});

function loadDataForProject(projectCode) {
    const storedData = localStorage.getItem(`trackerData_${projectCode}`);
    const storedFileName = localStorage.getItem(`trackerFileName_${projectCode}`);
    
    if (storedData) {
        currentData = JSON.parse(storedData);
        document.getElementById('lastUpdatedText').innerText = `Loaded: ${storedFileName || 'Saved Data'}`;
        updateDashboard();
    } else {
        currentData = [];
        document.getElementById('empty-state').classList.remove('hidden');
        document.getElementById('dashboard-content').classList.add('hidden');
        document.getElementById('lastUpdatedText').innerText = `No data loaded`;
    }
}

function updateDashboard() {
    if (!currentData || currentData.length === 0) return;

    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('dashboard-content').classList.remove('hidden');

    // --- CALCULATE KPIS ---
    const total = currentData.length;
    const ready = currentData.filter(d => {
        const s = (d['Job Status '] || d['Status'] || '').toLowerCase();
        return s.includes('ready') || s.includes('completed');
    }).length;
    
    const blockers = currentData.filter(d => {
        const p = (d['Pending On'] || '').toLowerCase();
        return p.includes('bank') || p.includes('client');
    }).length;

    document.getElementById('kpi-total').innerText = total;
    document.getElementById('kpi-readiness').innerText = total > 0 ? Math.round((ready / total) * 100) + '%' : '0%';
    document.getElementById('kpi-blocked').innerText = blockers;
    document.getElementById('kpi-pipeline').innerText = total - ready;

    // --- RENDER CHARTS ---
    renderCharts(currentData);

    // --- RENDER TIMELINE ---
    renderTimeline(currentData);

    // --- FILTER QUEUES ---
    const scribeQueue = currentData.filter(d => {
        const s = (d['Job Status '] || d['Status'] || '').toLowerCase();
        return s.includes('document') || s.includes('scribe');
    });

    const builderQueue = currentData.filter(d => {
        const s = (d['Job Status '] || d['Status'] || '').toLowerCase();
        return s.includes('dev') || s.includes('test') || s.includes('progress');
    });

    const orchestratorQueue = currentData.filter(d => !scribeQueue.includes(d) && !builderQueue.includes(d));

    // --- DRAW TABLES (EXACT FIX FOR ORCHESTRATOR) ---
    renderTable('table-orchestrator', orchestratorQueue, [
        'Module', 
        'Integration Touch Point', 
        'Assigned Resource', 
        'Pending On'
    ]);

    renderTable('table-scribe', scribeQueue, [
        'Integration Touch Point', 
        'Interface Type', 
        'Assigned Resource', 
        'Job Status '
    ]);

    renderTable('table-builder', builderQueue, [
        'Integration Touch Point', 
        'Assigned Resource', 
        'Start Date', 
        'End Date', 
        'Job Status '
    ]);
}

function renderTimeline(data) {
    const tbody = document.getElementById('timeline-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const timelineData = data
        .filter(r => r['End Date'] && r['End Date'].trim() !== '')
        .sort((a, b) => new Date(a['End Date']) - new Date(b['End Date']));

    timelineData.forEach(r => {
        const tp = r['Integration Touch Point'] || 'N/A';
        const res = r['Assigned Resource'] || 'Unassigned';
        const ed = r['End Date'];

        const tr = document.createElement('tr');
        tr.className = "border-b border-slate-100 last:border-0 hover:bg-slate-50";
        tr.innerHTML = `
            <td class="py-3 pr-4 text-slate-800 font-semibold text-xs truncate max-w-[150px]" title="${tp}">${tp}</td>
            <td class="py-3 pr-4 text-slate-500 text-xs font-medium">${res}</td>
            <td class="py-3"><span class="bg-slate-100 text-[#1B2955] px-2.5 py-1 rounded-md text-[10px] font-extrabold border border-slate-200 uppercase tracking-widest">${ed}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderTable(tableId, data, columns) {
    const table = document.getElementById(tableId);
    if (!table) return;

    let html = '<thead class="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider"><tr>';
    columns.forEach(col => {
        html += `<th class="px-4 py-3 font-semibold text-left">${col.trim()}</th>`;
    });
    html += '</tr></thead><tbody class="divide-y divide-slate-100">';

    data.forEach(row => {
        html += '<tr class="hover:bg-slate-50 transition-colors">';
        columns.forEach(col => {
            const val = row[col];
            html += `<td class="px-4 py-3 text-slate-700 text-sm whitespace-nowrap">${val ? val : '<span class="text-slate-300 italic">N/A</span>'}</td>`;
        });
        html += '</tr>';
    });

    if (data.length === 0) {
        html += `<tr><td colspan="${columns.length}" class="px-4 py-8 text-center text-slate-400 italic">Queue is empty</td></tr>`;
    }

    html += '</tbody>';
    table.innerHTML = html;
}

