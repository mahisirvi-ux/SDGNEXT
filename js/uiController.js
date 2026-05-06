export function initializeSidebar() {
    const buttons = document.querySelectorAll('.sidebar-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            // 1. Reset all sidebar buttons to inactive (Navy/Slate)
            buttons.forEach(b => {
                b.classList.remove('bg-[#E81F76]', 'text-white', 'shadow-lg', 'shadow-[#E81F76]/30');
                b.classList.add('hover:bg-[#2a3c75]', 'text-slate-400');
            });

            // 2. Activate the clicked button (Pink)
            const current = e.currentTarget;
            current.classList.remove('hover:bg-[#2a3c75]', 'text-slate-400');
            current.classList.add('bg-[#E81F76]', 'text-white', 'shadow-lg', 'shadow-[#E81F76]/30');

            // 3. Switch main views
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            const targetId = current.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

export function toggleEmptyState(hasData, timestamp = null) {
    const emptyState = document.getElementById('empty-state');
    const dashboardContent = document.getElementById('dashboard-content');
    const updateText = document.getElementById('lastUpdatedText');

    if (hasData) {
        emptyState.classList.add('hidden');
        dashboardContent.classList.remove('hidden');
        if(timestamp) updateText.innerText = `Last updated: ${timestamp}`;
    } else {
        emptyState.classList.remove('hidden');
        dashboardContent.classList.add('hidden');
        updateText.innerText = "No data loaded";
    }
}

// Metric & Table functions remain largely the same
export function updateKPIDisplay(kpis) {
    document.getElementById('kpi-total').innerText = kpis.total;
    document.getElementById('kpi-readiness').innerText = kpis.readiness;
    document.getElementById('kpi-blocked').innerText = kpis.bankBlocked;
    document.getElementById('kpi-pipeline').innerText = kpis.inPipeline;
}

export function renderTable(tableId, data, columns) {
    const table = document.getElementById(tableId);
    if (data.length === 0) {
        table.innerHTML = `<tbody><tr><td class="py-6 text-center text-slate-500 italic">Queue is currently empty.</td></tr></tbody>`;
        return;
    }
    let html = `<thead class="bg-slate-100 border-y border-slate-200"><tr>`;
    columns.forEach(col => html += `<th class="py-3 px-4 font-semibold text-slate-600">${col}</th>`);
    html += `</tr></thead><tbody class="divide-y divide-slate-100">`;
    data.slice(0, 15).forEach(row => {
        html += `<tr class="hover:bg-slate-50 transition-colors">`;
        columns.forEach(col => html += `<td class="py-3 px-4 text-slate-700 truncate max-w-xs">${row[col] || '-'}</td>`);
        html += `</tr>`;
    });
    html += `</tbody>`;
    table.innerHTML = html;
}