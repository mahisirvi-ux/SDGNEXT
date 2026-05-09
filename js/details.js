let currentData = null;

document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const id = urlParams.get('id');

    if (!id) {
        alert("No Touchpoint ID provided.");
        window.location.href = "/";
        return;
    }

    try {
        const response = await fetch(`/api/phase2/touchpoint/${id}`);
        const result = await response.json();

        if (response.ok && result.status === "success") {
            currentData = result.data;
            populatePage(currentData);
        } else {
            alert("Error loading data: " + result.message);
            window.location.href = "/";
        }
    } catch (err) {
        console.error(err);
        alert("Network Error. Ensure your Python backend is running without errors.");
    }
});

function populatePage(tp) {
    document.getElementById('fd-id').value = tp.id;
    document.getElementById('fd-integration-type').value = tp.integration || 'unassigned';
    
    // Header & Summary
    document.getElementById('fd-name').innerText = tp.name;
    document.getElementById('fd-module').innerText = tp.module;
    document.getElementById('fd-owner').innerText = tp.owner;
    document.getElementById('fd-status-badge').innerText = tp.techStatus;

    // --- 1. TOUCHPOINT DETAILS (Top Card Mapping) ---
    document.getElementById('fd-val-name').innerText = tp.name;
    document.getElementById('fd-val-module').innerText = tp.module;
    document.getElementById('fd-val-int').innerText = tp.integration || 'TBD';
    document.getElementById('fd-val-source').innerText = tp.source || '-';
    document.getElementById('fd-val-target').innerText = tp.target || '-';
    document.getElementById('fd-val-signoff').innerText = tp.signoff || 'Pending';
    
    document.getElementById('fd-val-mod-owner').innerText = tp.mod_owner || '-';
    document.getElementById('fd-val-tech-owner').innerText = tp.tech_owner_name || '-';
    document.getElementById('fd-val-fallback').innerText = tp.fallback || 'None';
    
    document.getElementById('fd-val-input').innerText = tp.input || 'Not specified';
    document.getElementById('fd-val-output').innerText = tp.output || 'Not specified';
    document.getElementById('fd-val-flow').innerText = tp.business_flow || 'No objective provided.';

    // Tracking Dates
    document.getElementById('fd-start').value = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start : "";
    document.getElementById('fd-end').value = (tp.end && tp.end !== "-" && tp.end !== "None") ? tp.end : "";

    // Technical JSON Data
    const td = tp.techDetails || {};
    document.getElementById('fd-criticality').value = td.criticality || "Medium";
    document.getElementById('fd-effort').value = td.effort || "";
    
    // Fill Workshop Notes & History
    document.getElementById('fd-discussion').value = td.discussion || "";
    document.getElementById('fd-pointers').value = tp.history_log || "";

    // API vs DB UI Toggle & Data mapping
    const intType = (tp.integration || "").toLowerCase();
    
    if (intType === 'api') {
        document.getElementById('fd-section-api').classList.remove('hidden');
        document.getElementById('fd-api-name').value = td.apiName || "";
        document.getElementById('fd-api-type').value = td.apiType || "REST";
        document.getElementById('fd-api-auth').value = td.apiAuth || "OAuth 2.0";
        document.getElementById('fd-api-url').value = td.apiUrl || "";
        document.getElementById('fd-api-method-name').value = td.apiMethodName || "";
        document.getElementById('fd-api-method').value = td.apiMethod || "GET";
        document.getElementById('fd-api-req').value = td.apiReq || "";
        document.getElementById('fd-api-res').value = td.apiRes || "";
    } else if (intType === 'database') {
        document.getElementById('fd-section-db').classList.remove('hidden');
        document.getElementById('fd-db-engine').value = td.dbEngine || "Oracle";
        document.getElementById('fd-db-target').value = td.dbTarget || "";
        document.getElementById('fd-db-account').value = td.dbAccount || "";
        document.getElementById('fd-db-firewall').value = td.dbFirewall || "";
    }
}

function toggleDetailsEditMode() {
    document.querySelectorAll('input, textarea, select').forEach(el => {
        if(el.type !== 'hidden') el.disabled = false;
    });
    
    // Clear out the pointers box so the user can type a NEW appended note easily
    const pointersBox = document.getElementById('fd-pointers');
    pointersBox.dataset.oldLog = pointersBox.value;
    pointersBox.value = "";
    pointersBox.placeholder = "Type a new update here to append it to the log...";

    document.getElementById('fd-btn-edit').classList.add('hidden');
    document.getElementById('fd-btn-save').classList.remove('hidden');
}

async function saveFullDetails() {
    const id = document.getElementById('fd-id').value;
    const intType = document.getElementById('fd-integration-type').value.toLowerCase();
    const saveBtn = document.getElementById('fd-btn-save');
    
    saveBtn.innerText = "Saving...";

    const techDetails = {
        discussion: document.getElementById('fd-discussion').value,
        pointers: document.getElementById('fd-pointers').value, // This sends the NEW appended note to backend
        criticality: document.getElementById('fd-criticality').value,
        effort: document.getElementById('fd-effort').value
    };

    if (intType === 'api') {
        techDetails.apiName = document.getElementById('fd-api-name').value;
        techDetails.apiType = document.getElementById('fd-api-type').value;
        techDetails.apiAuth = document.getElementById('fd-api-auth').value;
        techDetails.apiUrl = document.getElementById('fd-api-url').value;
        techDetails.apiMethodName = document.getElementById('fd-api-method-name').value;
        techDetails.apiMethod = document.getElementById('fd-api-method').value;
        techDetails.apiReq = document.getElementById('fd-api-req').value;
        techDetails.apiRes = document.getElementById('fd-api-res').value;
    } else if (intType === 'database') {
        techDetails.dbEngine = document.getElementById('fd-db-engine').value;
        techDetails.dbTarget = document.getElementById('fd-db-target').value;
        techDetails.dbAccount = document.getElementById('fd-db-account').value;
        techDetails.dbFirewall = document.getElementById('fd-db-firewall').value;
    }

    try {
        const response = await fetch(`/api/phase2/update/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                integration: currentData.integration, 
                start: document.getElementById('fd-start').value,
                end: document.getElementById('fd-end').value,
                status: currentData.techStatus,
                technical_details: techDetails
            })
        });
        
        if (response.ok) {
            // Reload the page to fetch the newly formatted log!
            window.location.reload();
        } else {
            alert("Error saving details.");
            saveBtn.innerText = "Save Changes";
        }
    } catch (err) {
        console.error(err);
        alert("Network error.");
        saveBtn.innerText = "Save Changes";
    }
}
async function generateWUD() {
    const id = document.getElementById('fd-id').value;
    const btn = document.getElementById('fd-btn-generate');
    const originalText = btn.innerText;
    
    // UI Feedback
    btn.innerText = "Generating AI PDF...";
    btn.disabled = true;
    btn.classList.add('opacity-75', 'cursor-wait');

    try {
        // Fetch the PDF binary stream
        const response = await fetch(`/api/phase2/touchpoint/${id}/generate-wud`);
        
        if (!response.ok) {
            // Handle if it's a JSON error (like "Only API supported")
            const errorData = await response.json();
            alert(errorData.message || "Failed to generate WUD.");
            return;
        }

        // Convert the response to a Blob (Binary Large Object)
        const blob = await response.blob();
        
        // Create a temporary hidden link to force the browser to download the file
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Extract filename from headers if possible, otherwise use a default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `WUD_Document_${id}.docx`;  // <-- Changed default fallback to .docx
        if (contentDisposition && contentDisposition.indexOf('filename=') !== -1) {
            filename = contentDisposition.split('filename=')[1].replace(/"/g, '');
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        
        // Clean up
        window.URL.revokeObjectURL(url);
        a.remove();

    } catch (err) {
        console.error(err);
        alert("Network error occurred while generating PDF.");
    } finally {
        // Restore button state
        btn.innerText = originalText;
        btn.disabled = false;
        btn.classList.remove('opacity-75', 'cursor-wait');
    }
}