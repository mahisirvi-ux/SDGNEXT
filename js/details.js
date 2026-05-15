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

    // Tracking Dates + Times. Backend sends 'YYYY-MM-DD HH:MM'; split into two inputs.
    const rawStart = (tp.start && tp.start !== "-" && tp.start !== "None") ? tp.start : "";
    const rawEnd   = (tp.end   && tp.end   !== "-" && tp.end   !== "None") ? tp.end   : "";
    const [sDate = "", sTime = ""] = rawStart.split(" ");
    const [eDate = "", eTime = ""] = rawEnd.split(" ");
    document.getElementById('fd-start').value = sDate;
    document.getElementById('fd-start-time').value = sTime;
    document.getElementById('fd-end').value = eDate;
    document.getElementById('fd-end-time').value = eTime;

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
    window.checkAndEnableMockButton(
        tp.integration,               // The integration type ('API', 'Database', etc)
        td.apiName || tp.name,        // The API Name (fallback to touchpoint name)
        td.apiMethod || 'POST',       // The HTTP Method
        td.apiRes || '{\n  "status": "success"\n}' // The Sample Response
    );
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

    // Recombine date + time inputs into the backend's expected 'YYYY-MM-DD HH:MM' format
    const combineDT = (dateId, timeId) => {
        const d = (document.getElementById(dateId)?.value || "").trim();
        if (!d) return "";
        const t = (document.getElementById(timeId)?.value || "").trim() || "00:00";
        return `${d} ${t}`;
    };

    try {
        const response = await fetch(`/api/phase2/update/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                integration: currentData.integration, 
                start: combineDT('fd-start', 'fd-start-time'),
                end:   combineDT('fd-end',   'fd-end-time'),
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
  window.toggleMockModal = function(show) {
            const modal = document.getElementById('mockServiceModal');
            const content = document.getElementById('mockModalContent');
            const resultArea = document.getElementById('mockResultArea');
            
            if (show) {
                // 1. Reset the form to blank immediately
                document.getElementById('mockServiceForm').reset();
                resultArea.classList.add('hidden');
                document.getElementById('mockSubmitBtn').disabled = false;
                document.getElementById('mockSubmitBtn').innerText = 'Deploy Service';
                
                // 2. Default back to the "Create" tab
                switchMockTab('create');
                
                modal.classList.remove('hidden');
                setTimeout(() => {
                    modal.classList.remove('opacity-0');
                    content.classList.remove('scale-95');
                    content.classList.add('scale-100');
                }, 10);
            } else {
                modal.classList.add('opacity-0');
                content.classList.remove('scale-100');
                content.classList.add('scale-95');
                setTimeout(() => {
                    modal.classList.add('hidden');
                }, 300);
            }
        };

        // Tab Switching Logic
        window.switchMockTab = function(tab) {
            const createTab = document.getElementById('mockCreateTab');
            const viewTab = document.getElementById('mockViewTab');
            const btnCreate = document.getElementById('tab-create');
            const btnView = document.getElementById('tab-view');
            
            if (tab === 'create') {
                createTab.classList.remove('hidden');
                viewTab.classList.add('hidden');
                btnCreate.className = 'pb-3 border-b-2 border-indigo-600 font-semibold text-indigo-600 transition-colors';
                btnView.className = 'pb-3 border-b-2 border-transparent font-medium text-slate-500 hover:text-slate-800 transition-colors';
            } else {
                createTab.classList.add('hidden');
                viewTab.classList.remove('hidden');
                btnView.className = 'pb-3 border-b-2 border-indigo-600 font-semibold text-indigo-600 transition-colors';
                btnCreate.className = 'pb-3 border-b-2 border-transparent font-medium text-slate-500 hover:text-slate-800 transition-colors';
                
                // Load existing mocks when viewing the tab
                document.getElementById('mockSearchInput').value = ''; 
                loadDeployedMocks(''); 
            }
        };

        // Fetch and Render Mocks
        window.loadDeployedMocks = async function(query) {
            const container = document.getElementById('mockListContainer');
            container.innerHTML = '<div class="text-center text-slate-500 py-6">Loading mocks...</div>';
            
            try {
                const res = await fetch(`/api/mocks/list?query=${encodeURIComponent(query)}`);
                const mocks = await res.json();
                
                if (mocks.length === 0) {
                    container.innerHTML = '<div class="text-center text-slate-500 py-6">No mocks found.</div>';
                    return;
                }
                
                let html = '';
                mocks.forEach(m => {
                    html += `
                    <div class="border border-slate-200 rounded-lg p-3 bg-white shadow-sm flex justify-between items-center hover:border-indigo-300 transition-colors">
                        <div>
                            <div class="flex items-center gap-2 mb-1">
                                <span class="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">${m.http_method}</span>
                                <span class="font-mono text-sm text-indigo-700 font-semibold">/${m.method_name}</span>
                            </div>
                            <p class="text-xs text-slate-500">Status: <span class="font-semibold text-slate-700">${m.status_code}</span> | ${m.content_type}</p>
                        </div>
                        <button type="button" onclick="copyGenericUrl('${window.location.origin}/mock-api/${m.method_name}', this)" class="text-slate-400 hover:text-indigo-600 bg-slate-50 hover:bg-indigo-50 p-2 rounded border border-slate-200 transition-colors" title="Copy URL">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
                        </button>
                    </div>
                    `;
                });
                container.innerHTML = html;
            } catch(e) {
                container.innerHTML = '<div class="text-center text-red-500 py-6">Error loading mocks.</div>';
            }
        };

        window.submitMockService = async function(event) {
            event.preventDefault(); 
            const submitBtn = document.getElementById('mockSubmitBtn');
            submitBtn.disabled = true;
            submitBtn.innerText = 'Deploying...';

            const payloadData = {
                method_name: document.getElementById('mockPath').value,
                http_method: document.getElementById('mockHttpMethod').value,
                status_code: parseInt(document.getElementById('mockStatus').value),
                content_type: document.getElementById('mockContentType').value,
                payload: document.getElementById('mockPayload').value,
                created_by: "System User"
            };

            try {
                const response = await fetch('/api/mocks/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payloadData)
                });

                const result = await response.json();

                if (response.ok) {
                    const fullUrl = window.location.origin + result.mock_url;
                    document.getElementById('mockFinalUrl').innerText = fullUrl;
                    document.getElementById('mockResultArea').classList.remove('hidden');
                    submitBtn.innerText = 'Deployed!';
                } else {
                    // 🚨 SHOWS THE ERROR ALERT TO THE USER IF IT ALREADY EXISTS
                    alert(result.detail || 'Failed to deploy mock.');
                    submitBtn.disabled = false;
                    submitBtn.innerText = 'Deploy Service';
                }
            } catch (error) {
                console.error('Error deploying mock:', error);
                alert('Network error while deploying mock.');
                submitBtn.disabled = false;
                submitBtn.innerText = 'Deploy Service';
            }
        };

        // Copies URL from the success box
        window.copyMockUrl = function() {
            const urlText = document.getElementById('mockFinalUrl').innerText;
            navigator.clipboard.writeText(urlText).then(() => {
                const btn = event.target;
                const originalText = btn.innerText;
                btn.innerText = 'Copied!';
                btn.classList.replace('bg-emerald-600', 'bg-emerald-800');
                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.classList.replace('bg-emerald-800', 'bg-emerald-600');
                }, 2000);
            });
        };

        // Copies URL directly from the list view
        window.copyGenericUrl = function(urlText, btnElement) {
            navigator.clipboard.writeText(urlText).then(() => {
                const originalHTML = btnElement.innerHTML;
                btnElement.innerHTML = '<svg class="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>';
                setTimeout(() => {
                    btnElement.innerHTML = originalHTML;
                }, 1500);
            });
        };
  // 1. THE CHECKER: Call this function whenever your Phase 2 Detail page opens!
window.checkAndEnableMockButton = function(integrationType, apiName, httpMethod, sampleResponse) {
    const mockBtn = document.getElementById('detailDeployMockBtn');
    if (!mockBtn) return;

    // Make it case-insensitive and check if it's 'api'
    const isApi = integrationType && integrationType.toString().trim().toLowerCase() === 'api';

    if (isApi) {
        // ✅ Enable the button and make it beautiful
        mockBtn.disabled = false;
        mockBtn.className = "flex items-center gap-2 bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 text-white font-semibold py-2 px-4 rounded-lg shadow-md hover:shadow-lg transition-all transform hover:-translate-y-0.5";
        mockBtn.title = "Deploy this integration as a Mock API";
        
        // Store the details inside the button's dataset for later
        mockBtn.dataset.apiname = apiName || '';
        mockBtn.dataset.method = httpMethod || 'POST';
        mockBtn.dataset.response = sampleResponse || '{\n  "status": "success"\n}';
        
    } else {
        // ❌ Disable the button for File/DB/SFTP types
        mockBtn.disabled = true;
        mockBtn.className = "flex items-center gap-2 bg-slate-400 text-white font-semibold py-2 px-4 rounded-lg shadow-sm opacity-50 cursor-not-allowed transition-all";
        mockBtn.title = `Mocks cannot be deployed for type: ${integrationType || 'Unknown'}. Only APIs are supported.`;
    }
};

// 2. THE EXECUTOR: This runs when the user clicks the active button
window.openPrepopulatedMockModal = function() {
    const mockBtn = document.getElementById('detailDeployMockBtn');
    if (mockBtn.disabled) return;

    // Grab the stored data from the button
    const rawApiName = mockBtn.dataset.apiname || 'new-endpoint';
    const rawMethod = mockBtn.dataset.method.toUpperCase();
    const rawResponse = mockBtn.dataset.response;

    // 1. Format the endpoint path (e.g. "Create Lead" -> "create-lead")
    const cleanPath = rawApiName.replace(/\s+/g, '-').toLowerCase();

    // 2. Open the modal (using your existing function)
    window.toggleMockModal(true);

    // 3. Pre-fill the Endpoint Path
    document.getElementById('mockPath').value = cleanPath;
    
    // 4. Pre-fill the HTTP Method (Fallback to POST if missing)
    const methodDropdown = document.getElementById('mockHttpMethod');
    if([...methodDropdown.options].some(opt => opt.value === rawMethod)) {
        methodDropdown.value = rawMethod;
    } else {
        methodDropdown.value = "POST"; 
    }

    // 5. Pre-fill the Response Payload & Auto-Detect Type
    const payloadBox = document.getElementById('mockPayload');
    const typeDropdown = document.getElementById('mockContentType');
    
    try {
        // If it's valid JSON, format it with nice indents!
        const parsedJson = JSON.parse(rawResponse);
        payloadBox.value = JSON.stringify(parsedJson, null, 2);
        typeDropdown.value = "application/json";
    } catch (e) {
        // If it fails to parse as JSON, check if it looks like XML
        payloadBox.value = rawResponse;
        if (rawResponse.trim().startsWith('<')) {
            typeDropdown.value = "application/xml";
        } else {
            typeDropdown.value = "text/plain";
        }
    }
};