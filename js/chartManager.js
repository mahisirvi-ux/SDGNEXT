let typeChartInstance = null;
let blockerChartInstance = null;
let resourceChartInstance = null; // Track the new resource chart

export function renderCharts(data) {
    const types = {};
    const pending = {};
    const resources = {}; // Object to hold resource assignments

    // Aggregate data
    data.forEach(r => {
        const type = r['Interface Type'] || 'Unknown';
        const p = r['Pending On'] || 'Unassigned';
        const res = r['Assigned Resource'] || 'Unassigned'; // Fetch assigned resource

        types[type] = (types[type] || 0) + 1;
        pending[p] = (pending[p] || 0) + 1;
        resources[res] = (resources[res] || 0) + 1; // Increment count for the resource
    });

    // Destroy existing charts to prevent rendering bugs
    if(typeChartInstance) typeChartInstance.destroy();
    if(blockerChartInstance) blockerChartInstance.destroy();
    if(resourceChartInstance) resourceChartInstance.destroy(); // Destroy existing resource chart

    // Render Bar Chart (Interface Types)
    typeChartInstance = new Chart(document.getElementById('typeChart'), {
        type: 'bar',
        data: {
            labels: Object.keys(types),
            datasets: [{
                label: 'Count',
                data: Object.values(types),
                backgroundColor: '#E81F76', 
                borderRadius: 4
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
    });

    // Render Donut Chart (Blockers)
    blockerChartInstance = new Chart(document.getElementById('blockerChart'), {
        type: 'doughnut',
        data: {
            labels: Object.keys(pending),
            datasets: [{
                data: Object.values(pending),
                backgroundColor: ['#E81F76', '#1B2955', '#4B5563', '#EB89B9', '#64748B'] 
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, cutout: '65%' }
    });

    // Render Resource Workload Chart (Horizontal Bar)
    resourceChartInstance = new Chart(document.getElementById('resourceChart'), {
        type: 'bar',
        data: {
            labels: Object.keys(resources),
            datasets: [{
                label: 'Assigned Integrations',
                data: Object.values(resources),
                backgroundColor: '#1B2955', // BusinessNext Navy
                borderRadius: 4
            }]
        },
        options: { 
            indexAxis: 'y', // Turns the standard bar chart into a horizontal bar chart
            responsive: true, 
            maintainAspectRatio: false, 
            plugins: { legend: { display: false } },
            scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } // Ensure whole numbers for counts
        }
    });
}