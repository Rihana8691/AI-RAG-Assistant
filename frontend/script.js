// =========================
// Configuration
// =========================

const CONFIG = {
    API_BASE_URL: "http://127.0.0.1:8000"
};

// =========================
// State & Persistence
// =========================

let conversations = JSON.parse(localStorage.getItem('rag_conversations')) || [];
let uploadedDocuments = [];
let currentConversationId = localStorage.getItem('rag_current_conv_id') || null;
let isAnswering = false;

// Selection State
let pendingFiles = [];
let uploadAbortController = null;

// Initial load
window.addEventListener('DOMContentLoaded', () => {
    updateConversationHistory();
    syncDocumentsWithBackend();
    if (currentConversationId) {
        loadConversation(currentConversationId);
    }
});

function saveState() {
    localStorage.setItem('rag_conversations', JSON.stringify(conversations));
    localStorage.setItem('rag_current_conv_id', currentConversationId);
}

// =========================
// UI Logic
// =========================

async function syncDocumentsWithBackend() {
    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/documents`);
        if (!response.ok) return;
        const data = await response.json();
        if (data.documents) {
            uploadedDocuments = data.documents;
            updateDocumentList();
        }
    } catch (e) {
        console.warn("Could not reach backend for document list.");
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');
}

function toggleUploadModal() {
    const modal = document.getElementById('uploadModal');
    modal.classList.toggle('hidden');

    // Clear selection if closing
    if (modal.classList.contains('hidden')) {
        pendingFiles = [];
        updateFilePreview();
        document.getElementById('uploadStatus').innerHTML = '';
        document.getElementById('uploadProgress').classList.add('hidden');
        document.getElementById('uploadButton').classList.add('hidden');
    }
}

function newChat() {
    if (isAnswering) return;

    currentConversationId = Date.now().toString();
    const newConv = {
        id: currentConversationId,
        title: 'New chat',
        messages: [],
        timestamp: new Date().toISOString()
    };

    conversations.unshift(newConv);
    renderMessages([]);
    updateConversationHistory();
    saveState();
}

function updateConversationHistory() {
    const historyDiv = document.getElementById('conversationHistory');
    if (!historyDiv) return;

    historyDiv.innerHTML = conversations.map(conv => `
        <div class="group flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer ${conv.id === currentConversationId ? 'bg-zinc-800' : ''}" onclick="loadConversation('${conv.id}')">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <span class="flex-1 text-sm text-zinc-300 truncate">${conv.title}</span>
            <button onclick="deleteConversation(event, '${conv.id}')" class="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
            </button>
        </div>
    `).join('');
}

function updateDocumentList() {
    const listDiv = document.getElementById('documentList');
    if (!listDiv) return;

    if (uploadedDocuments.length === 0) {
        listDiv.innerHTML = `<p class="italic opacity-50 px-3 text-[10px]">No documents uploaded</p>`;
        return;
    }

    listDiv.innerHTML = uploadedDocuments.map(doc => `
        <div class="flex items-center gap-2 px-3 py-1.5 group hover:bg-zinc-800/50 rounded-md transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 shrink-0 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <a
                href="${CONFIG.API_BASE_URL}/view-documents/${encodeURIComponent(doc)}"
                target="_blank"
                class="truncate flex-1 text-[11px] text-zinc-400 font-medium hover:text-indigo-400 hover:underline transition-all"
                title="Click to open ${doc}"
            >
                ${doc}
            </a>
            <button onclick="removeDocumentFromServer('${doc}')" class="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-all p-0.5">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
    `).join('');
}

async function removeDocumentFromServer(filename) {
    if (!confirm(`Are you sure you want to remove "${filename}"? AI will re-index remaining documents.`)) return;

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/documents/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            await syncDocumentsWithBackend();
        }
    } catch (e) {
        console.error("Delete request error:", e);
    }
}

function loadConversation(id) {
    if (isAnswering) return;

    const conv = conversations.find(c => c.id === id);
    if (!conv) return;

    currentConversationId = id;
    renderMessages(conv.messages);
    updateConversationHistory();
    saveState();
}

function deleteConversation(e, id) {
    e.stopPropagation();
    conversations = conversations.filter(c => c.id !== id);
    if (currentConversationId === id) {
        currentConversationId = null;
        document.getElementById('chat').innerHTML = '';
        showPlaceholder();
    }
    updateConversationHistory();
    saveState();
}

function showPlaceholder() {
    const chat = document.getElementById('chat');
    chat.innerHTML = `
        <div id="chatPlaceholder" class="h-full flex flex-col items-center justify-center text-zinc-500">
            <div class="text-3xl mb-4">📚</div>
            <p class="text-lg font-medium mb-2 text-white">How can I help you today?</p>
            <p class="text-sm">Upload PDFs to unlock intelligence</p>
        </div>
    `;
}

function renderMessages(messages) {
    const chat = document.getElementById('chat');
    chat.innerHTML = '';

    if (messages.length === 0) {
        showPlaceholder();
        return;
    }

    messages.forEach(msg => {
        if (msg.role === 'user') {
            appendUserMessageUI(msg.content);
        } else {
            appendAIMessageUI(msg.content, msg.sources, false);
        }
    });
    chat.scrollTop = chat.scrollHeight;
}

const mainInput = document.getElementById('question');
if (mainInput) {
    mainInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
}

function handleKeyDown(event) {
    if (isAnswering) return;
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        askQuestion();
    }
}

// =========================
// File Selection Preview
// =========================

function updateFilePreview() {
    const previewArea = document.getElementById('filePreviewArea');
    const list = document.getElementById('selectedFilesList');
    const uploadBtn = document.getElementById('uploadButton');

    if (pendingFiles.length === 0) {
        previewArea.classList.add('hidden');
        uploadBtn.classList.add('hidden');
        return;
    }

    previewArea.classList.remove('hidden');
    uploadBtn.classList.remove('hidden');

    list.innerHTML = pendingFiles.map((f, index) => `
        <div class="flex items-center gap-2 bg-zinc-800/40 p-2 rounded-lg border border-zinc-700/30 group">
            <svg class="h-4 w-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
            <span class="text-xs text-zinc-300 truncate flex-1">${f.name}</span>
            <button onclick="removeFileFromSelection(${index})" class="p-1 text-zinc-600 hover:text-red-400 transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
    `).join('');
}

function removeFileFromSelection(index) {
    pendingFiles.splice(index, 1);
    updateFilePreview();
}

function cancelUpload() {
    if (uploadAbortController) {
        uploadAbortController.abort();
        uploadAbortController = null;

        const stepText = document.getElementById('uploadStepText');
        stepText.innerText = "Upload Canceled";

        setTimeout(() => {
            document.getElementById('uploadProgress').classList.add('hidden');
            document.getElementById('dropZone').classList.remove('pointer-events-none', 'opacity-50');
            document.getElementById('uploadStatus').innerHTML = '';
        }, 1500);
    }
}

// =========================
// File Management
// =========================

const pdfFileEl = document.getElementById("pdfFiles");
if (pdfFileEl) {
    pdfFileEl.addEventListener("change", function () {
        if (this.files.length > 0) {
            Array.from(this.files).forEach(f => pendingFiles.push(f));
            updateFilePreview();
            this.value = ""; // Reset input so same file can be chosen again
        }
    });
}

const dzBox = document.getElementById('dropZone');
if (dzBox) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dzBox.addEventListener(eventName, e => { e.preventDefault(); e.stopPropagation(); }, false);
    });
    dzBox.addEventListener('dragover', () => dzBox.classList.add('bg-indigo-500/5', 'border-indigo-500'));
    ['dragleave', 'drop'].forEach(eventName => {
        dzBox.addEventListener(eventName, () => dzBox.classList.remove('bg-indigo-500/5', 'border-indigo-500'));
    });
    dzBox.addEventListener('drop', e => {
        const files = e.dataTransfer.files;
        const pdfFilesOnly = Array.from(files).filter(file => file.type === 'application/pdf');
        if (pdfFilesOnly.length > 0) {
            pdfFilesOnly.forEach(f => pendingFiles.push(f));
            updateFilePreview();
        }
    });
}

async function uploadPDFs() {
    const progressDiv = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');
    const stepText = document.getElementById('uploadStepText');
    const dzElement = document.getElementById('dropZone');
    const uploadBtn = document.getElementById('uploadButton');

    if (pendingFiles.length === 0) return;

    uploadAbortController = new AbortController();
    const formData = new FormData();
    pendingFiles.forEach(file => formData.append("files", file));

    // UI state
    progressDiv.classList.remove('hidden');
    uploadBtn.classList.add('hidden');
    dzElement.classList.add('pointer-events-none', 'opacity-50');
    stepText.innerText = "Connecting to server...";
    progressBar.style.width = '0%';
    progressPercent.innerText = '0%';

    let progressValue = 0;
    const progressInterval = setInterval(() => {
        progressValue += Math.random() * 5;
        if (progressValue > 95) {
            progressValue = 95;
            stepText.innerText = "Analyzing text & building vector memory...";
        } else if (progressValue > 50) {
            stepText.innerText = "Parsing document structure...";
        } else if (progressValue > 10) {
            stepText.innerText = `Sending ${pendingFiles.length} file(s)...`;
        }
        progressBar.style.width = progressValue + '%';
        progressPercent.innerText = Math.round(progressValue) + '%';
    }, 500);

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/upload`, {
            method: "POST",
            body: formData,
            signal: uploadAbortController.signal
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);

        const data = await response.json();
        clearInterval(progressInterval);

        if (data.success) {
            progressBar.style.width = '100%';
            progressPercent.innerText = '100%';
            stepText.innerText = "Successfully Indexed!";
            await syncDocumentsWithBackend();
            pendingFiles = [];
            setTimeout(() => toggleUploadModal(), 1500);
        } else {
            throw new Error(data.message);
        }
    } catch (error) {
        clearInterval(progressInterval);
        if (error.name === 'AbortError') {
            console.log("Upload aborted by user");
        } else {
            stepText.innerText = "Upload Failed";
            progressBar.classList.add('bg-red-500');
            document.getElementById('uploadStatus').innerHTML = `<span class="text-red-500 text-xs">${error.message}</span>`;
            dzElement.classList.remove('pointer-events-none', 'opacity-50');
        }
    }
}

// =========================
// Chat UI Helpers
// =========================

function appendUserMessageUI(content) {
    const chat = document.getElementById("chat");
    const userMessageDiv = document.createElement("div");
    userMessageDiv.className = "user-message";
    userMessageDiv.innerHTML = `
        <div class="max-w-3xl mx-auto flex gap-4">
            <div class="w-8 h-8 rounded-full bg-zinc-700 flex items-center justify-center shrink-0 text-xs font-bold text-white">U</div>
            <div class="text-white font-medium flex-1 pt-1 whitespace-pre-wrap">${DOMPurify.sanitize(content)}</div>
        </div>
    `;
    chat.appendChild(userMessageDiv);
}

function appendAIMessageUI(content, sources, isLoading) {
    const chat = document.getElementById("chat");
    const id = "msg-" + Date.now() + Math.random().toString(36).substr(2, 9);
    const aiMessageDiv = document.createElement("div");
    aiMessageDiv.id = id;
    aiMessageDiv.className = "ai-message bg-zinc-800/20";

    if (isLoading) {
        aiMessageDiv.innerHTML = `
            <div class="max-w-3xl mx-auto flex gap-4">
                <div class="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center shrink-0">
                    <svg class="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>
                </div>
                <div class="flex-1 pt-1 text-white">
                    <div class="flex gap-1.5 items-center h-6">
                        <span class="typing-dot animate-bounce" style="animation-delay: 0ms"></span>
                        <span class="typing-dot animate-bounce" style="animation-delay: 150ms"></span>
                        <span class="typing-dot animate-bounce" style="animation-delay: 300ms"></span>
                    </div>
                </div>
            </div>
        `;
    } else {
        const sanitizedContent = DOMPurify.sanitize(marked.parse(content || ""));
        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            sourcesHtml = `
                <div class="mt-4 pt-3 border-t border-zinc-800">
                    <details class="group">
                        <summary class="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer hover:text-zinc-300 transition-colors font-bold uppercase tracking-wider">
                            <svg class="h-3 w-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M9 5l7 7-7 7"/></svg>
                            View ${sources.length} Citations
                        </summary>
                        <div class="mt-2 space-y-3 pl-5">
                            ${sources.map(s => `
                                <div class="bg-zinc-800/40 p-3 rounded-lg border border-zinc-700/50">
                                    <div class="text-[10px] text-emerald-400 font-bold mb-1">${DOMPurify.sanitize(typeof s === 'string' ? s : s.source)}</div>
                                    ${s.snippet ? `<div class="text-xs text-zinc-400 italic line-clamp-3 leading-relaxed">"${DOMPurify.sanitize(s.snippet)}"</div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </details>
                </div>
            `;
        }
        aiMessageDiv.innerHTML = `
            <div class="max-w-3xl mx-auto flex gap-4">
                <div class="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center shrink-0">
                    <svg class="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>
                </div>
                <div class="flex-1 pt-1 overflow-hidden">
                    <div class="markdown-content text-white text-base leading-relaxed">${sanitizedContent}</div>
                    ${sourcesHtml}
                </div>
            </div>
        `;
    }
    chat.appendChild(aiMessageDiv);
    return id;
}

async function askQuestion() {
    if (isAnswering) return;
    const input = document.getElementById("question");
    const chat = document.getElementById("chat");
    const sendButton = document.getElementById("sendButton");
    const question = input.value.trim();
    if (question === "") return;

    isAnswering = true;
    if (sendButton) { sendButton.disabled = true; sendButton.classList.add('opacity-50', 'cursor-not-allowed'); }
    input.value = ""; input.style.height = 'auto';
    const placeholder = document.getElementById("chatPlaceholder");
    if (placeholder) placeholder.remove();

    if (!currentConversationId) {
        currentConversationId = Date.now().toString();
        conversations.unshift({ id: currentConversationId, title: question.substring(0, 30) + '...', messages: [], timestamp: new Date().toISOString() });
        updateConversationHistory();
    } else {
        const conv = conversations.find(c => c.id === currentConversationId);
        if (conv && conv.title === 'New chat') { conv.title = question.substring(0, 30) + '...'; updateConversationHistory(); }
    }

    const currentConv = conversations.find(c => c.id === currentConversationId);
    const history = currentConv.messages.slice(-10).map(m => ({ role: m.role, content: m.content }));
    currentConv.messages.push({ role: 'user', content: question });
    saveState();

    appendUserMessageUI(question);
    const loadingId = appendAIMessageUI("", [], true);
    chat.scrollTop = chat.scrollHeight;

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/ask-stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, history })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullAnswer = "";
        let sources = [];
        const messageDiv = document.getElementById(loadingId);
        messageDiv.querySelector('.flex-1').innerHTML = `<div class="markdown-content text-white text-base leading-relaxed streaming-content"></div><div class="sources-container mt-4"></div>`;
        const contentDiv = messageDiv.querySelector('.streaming-content');

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            chunk.split('\n').forEach(line => {
                if (line.trim().startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.trim().slice(6));
                        if (data.type === 'token') {
                            fullAnswer += data.content;
                            contentDiv.innerHTML = DOMPurify.sanitize(marked.parse(fullAnswer));
                            messageDiv.querySelectorAll('pre code').forEach(block => { if (!block.dataset.highlighted) { hljs.highlightElement(block); block.dataset.highlighted = "true"; } });
                            chat.scrollTop = chat.scrollHeight;
                        } else if (data.type === 'sources') { sources = data.sources; }
                    } catch (e) {}
                }
            });
        }
        currentConv.messages.push({ role: 'assistant', content: fullAnswer, sources });
        saveState();
        if (sources.length > 0) {
            messageDiv.querySelector('.sources-container').innerHTML = `<div class="mt-4 pt-3 border-t border-zinc-800"><details class="group"><summary class="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer hover:text-zinc-300 font-bold uppercase tracking-wider"><svg class="h-3 w-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M9 5l7 7-7 7"/></svg>View ${sources.length} Citations</summary><div class="mt-2 space-y-3 pl-5">${sources.map(s => `<div class="bg-zinc-800/40 p-3 rounded-lg border border-zinc-700/50"><div class="text-[10px] text-emerald-400 font-bold mb-1">${DOMPurify.sanitize(typeof s === 'string' ? s : s.source)}</div>${s.snippet ? `<div class="text-xs text-zinc-400 italic line-clamp-3 leading-relaxed">"${DOMPurify.sanitize(s.snippet)}"</div>` : ''}</div>`).join('')}</div></details></div>`;
        }
    } catch (err) {
        if (document.getElementById(loadingId)) {
            document.getElementById(loadingId).querySelector('.flex-1').innerHTML = `<p class="text-red-500 text-sm">Connection failed.</p>`;
        }
    } finally {
        isAnswering = false;
        if (sendButton) { sendButton.disabled = false; sendButton.classList.remove('opacity-50', 'cursor-not-allowed'); }
        const qInput = document.getElementById('question');
        if (qInput) qInput.focus();
    }
}

// =========================
// Utilities
// =========================

function copyToClipboard(button, text) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
        const original = button.innerHTML;
        button.innerHTML = "Copied!";
        button.classList.add('text-emerald-500');
        setTimeout(() => { button.innerHTML = original; button.classList.remove('text-emerald-500'); }, 2000);
    });
}

function exportChat() {
    if (!currentConversationId) return alert('No active chat');
    const conv = conversations.find(c => c.id === currentConversationId);
    if (!conv || conv.messages.length === 0) return alert('Empty');
    let text = `Export - ${conv.title}\n` + '='.repeat(40) + '\n\n';
    conv.messages.forEach(msg => { text += `${msg.role.toUpperCase()}:\n${msg.content}\n\n`; });
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' })); a.download = `chat-${conv.id}.txt`; a.click();
}