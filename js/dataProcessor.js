// Local Storage Handlers for Multi-Project Support
export function saveProjectData(projectName, data) {
    localStorage.setItem(`sdgnext_${projectName}`, JSON.stringify({
        timestamp: new Date().toLocaleString(),
        payload: data
    }));
}

export function loadProjectData(projectName) {
    const rawData = localStorage.getItem(`sdgnext_${projectName}`);
    if (rawData) {
        return JSON.parse(rawData); // Returns { timestamp, payload }
    }
    return null;
}

// Data Cleaning
export function cleanData(rawData) {
    return rawData.map(row => {
        let clean = {};
        for (let key in row) clean[key.trim()] = row[key];
        return clean;
    });
}

// Analytics Calculations
export function calculateKPIs(data) {
    const total = data.length;
    const completed = data.filter(r => r['WUD Status'] === 'Completed').length;
    const bankBlocked = data.filter(r => (r['Pending On'] || '').includes('Bank')).length;
    return {
        total,
        readiness: total ? ((completed / total) * 100).toFixed(0) + '%' : '0%',
        bankBlocked,
        inPipeline: total - completed
    };
}

// Agent Queue Segmenting
export function getAgentQueues(data) {
    return {
        orchestratorQueue: data.filter(r => r['WUD Status'] !== 'Completed'),
        scribeQueue: data.filter(r => r['WUD Status'] === 'Completed' && r['API Available'] === 'No'),
        builderQueue: data.filter(r => r['WUD Status'] === 'Completed' && r['API Available'] === 'Available')
    };
}