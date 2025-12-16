// LLM Chat Application

class LLMChat {
    constructor() {
        this.messages = [];
        this.skills = [];
        this.isStreaming = false;
        this.abortController = null;
        
        this.initElements();
        this.initEventListeners();
        this.loadFromStorage();
        this.updateContextMeter();
    }

    initElements() {
        // Sidebar
        this.sidebar = document.getElementById('sidebar');
        this.openSidebarBtn = document.getElementById('openSidebar');
        this.closeSidebarBtn = document.getElementById('closeSidebar');
        
        // Config inputs
        this.apiEndpointInput = document.getElementById('apiEndpoint');
        this.modelNameInput = document.getElementById('modelName');
        this.enableReasoningCheckbox = document.getElementById('enableReasoning');
        this.reasoningBudgetInput = document.getElementById('reasoningBudget');
        this.reasoningBudgetGroup = document.getElementById('reasoningBudgetGroup');
        this.systemPromptInput = document.getElementById('systemPrompt');
        this.maxContextTokensInput = document.getElementById('maxContextTokens');
        
        // Context meter
        this.contextFill = document.getElementById('contextFill');
        this.contextUsed = document.getElementById('contextUsed');
        this.contextMax = document.getElementById('contextMax');
        
        // Skills
        this.skillsList = document.getElementById('skillsList');
        this.addSkillBtn = document.getElementById('addSkillBtn');
        
        // Chat
        this.chatMessages = document.getElementById('chatMessages');
        this.userInput = document.getElementById('userInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.stopBtn = document.getElementById('stopBtn');
        this.modelDisplay = document.getElementById('modelDisplay');
        
        // Drop overlay
        this.dropOverlay = document.getElementById('dropOverlay');
        
        // Import/Export
        this.exportBtn = document.getElementById('exportBtn');
        this.importBtn = document.getElementById('importBtn');
        this.importFile = document.getElementById('importFile');
        this.clearBtn = document.getElementById('clearBtn');
        
        // Modal
        this.skillModal = document.getElementById('skillModal');
        this.skillModalTitle = document.getElementById('skillModalTitle');
        this.skillNameInput = document.getElementById('skillName');
        this.skillContentInput = document.getElementById('skillContent');
        this.saveSkillBtn = document.getElementById('saveSkillBtn');
        this.cancelSkillBtn = document.getElementById('cancelSkillBtn');
        this.deleteSkillBtn = document.getElementById('deleteSkillBtn');
        this.closeSkillModalBtn = document.getElementById('closeSkillModal');
        
        this.editingSkillIndex = null;
    }

    initEventListeners() {
        // Sidebar toggle
        this.openSidebarBtn.addEventListener('click', () => this.toggleSidebar(true));
        this.closeSidebarBtn.addEventListener('click', () => this.toggleSidebar(false));
        
        // Config changes
        this.apiEndpointInput.addEventListener('change', () => this.saveToStorage());
        this.modelNameInput.addEventListener('change', () => {
            this.updateModelDisplay();
            this.saveToStorage();
        });
        this.enableReasoningCheckbox.addEventListener('change', () => {
            this.toggleReasoningBudget();
            this.saveToStorage();
        });
        this.reasoningBudgetInput.addEventListener('change', () => this.saveToStorage());
        this.systemPromptInput.addEventListener('input', () => {
            this.updateContextMeter();
            this.saveToStorage();
        });
        this.maxContextTokensInput.addEventListener('change', () => {
            this.updateContextMeter();
            this.saveToStorage();
        });
        
        // Skills
        this.addSkillBtn.addEventListener('click', () => this.openSkillModal());
        this.saveSkillBtn.addEventListener('click', () => this.saveSkill());
        this.cancelSkillBtn.addEventListener('click', () => this.closeSkillModal());
        this.deleteSkillBtn.addEventListener('click', () => this.deleteSkill());
        this.closeSkillModalBtn.addEventListener('click', () => this.closeSkillModal());
        
        // Chat
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.stopBtn.addEventListener('click', () => this.stopGeneration());
        
        // Input handling
        this.userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        this.userInput.addEventListener('input', () => {
            this.autoResizeTextarea();
            this.updateContextMeter();
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isStreaming) {
                this.stopGeneration();
            }
        });
        
        // Drag and drop
        const chatMain = document.querySelector('.chat-main');
        chatMain.addEventListener('dragover', (e) => this.handleDragOver(e));
        chatMain.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        chatMain.addEventListener('drop', (e) => this.handleDrop(e));
        
        // Import/Export
        this.exportBtn.addEventListener('click', () => this.exportConversation());
        this.importBtn.addEventListener('click', () => this.importFile.click());
        this.importFile.addEventListener('change', (e) => this.importConversation(e));
        this.clearBtn.addEventListener('click', () => this.clearConversation());
        
        // Close modal on outside click
        this.skillModal.addEventListener('click', (e) => {
            if (e.target === this.skillModal) {
                this.closeSkillModal();
            }
        });
    }

    // Sidebar
    toggleSidebar(open) {
        this.sidebar.classList.toggle('collapsed', !open);
    }

    // Model display
    updateModelDisplay() {
        const model = this.modelNameInput.value || 'No model set';
        this.modelDisplay.textContent = model;
    }

    // Reasoning toggle
    toggleReasoningBudget() {
        const enabled = this.enableReasoningCheckbox.checked;
        this.reasoningBudgetGroup.style.display = enabled ? 'block' : 'none';
    }

    // Auto-resize textarea
    autoResizeTextarea() {
        this.userInput.style.height = 'auto';
        this.userInput.style.height = Math.min(this.userInput.scrollHeight, 200) + 'px';
    }

    // Context meter
    updateContextMeter() {
        const maxTokens = parseInt(this.maxContextTokensInput.value) || 128000;
        const estimatedTokens = this.estimateTokens();
        
        const percentage = Math.min((estimatedTokens / maxTokens) * 100, 100);
        
        this.contextFill.style.width = percentage + '%';
        this.contextFill.classList.remove('warning', 'danger');
        
        if (percentage > 90) {
            this.contextFill.classList.add('danger');
        } else if (percentage > 70) {
            this.contextFill.classList.add('warning');
        }
        
        this.contextUsed.textContent = estimatedTokens.toLocaleString();
        this.contextMax.textContent = maxTokens.toLocaleString();
    }

    estimateTokens() {
        // Rough estimation: ~4 characters per token
        let totalChars = 0;
        
        // System prompt
        totalChars += (this.systemPromptInput.value || '').length;
        
        // Active skills
        this.skills.forEach(skill => {
            if (skill.enabled) {
                totalChars += skill.content.length;
            }
        });
        
        // Messages
        this.messages.forEach(msg => {
            totalChars += msg.content.length;
            if (msg.thinking) {
                totalChars += msg.thinking.length;
            }
        });
        
        // Current input
        totalChars += (this.userInput.value || '').length;
        
        return Math.ceil(totalChars / 4);
    }

    // Skills management
    renderSkills() {
        this.skillsList.innerHTML = '';
        
        this.skills.forEach((skill, index) => {
            const item = document.createElement('div');
            item.className = 'skill-item';
            item.innerHTML = `
                <input type="checkbox" ${skill.enabled ? 'checked' : ''} data-index="${index}">
                <span class="skill-name">${this.escapeHtml(skill.name)}</span>
                <button class="skill-edit" data-index="${index}">Edit</button>
            `;
            
            item.querySelector('input').addEventListener('change', (e) => {
                this.skills[index].enabled = e.target.checked;
                this.updateContextMeter();
                this.saveToStorage();
            });
            
            item.querySelector('.skill-edit').addEventListener('click', (e) => {
                e.stopPropagation();
                this.openSkillModal(index);
            });
            
            this.skillsList.appendChild(item);
        });
    }

    openSkillModal(index = null) {
        this.editingSkillIndex = index;
        
        if (index !== null) {
            const skill = this.skills[index];
            this.skillModalTitle.textContent = 'Edit Skill';
            this.skillNameInput.value = skill.name;
            this.skillContentInput.value = skill.content;
            this.deleteSkillBtn.hidden = false;
        } else {
            this.skillModalTitle.textContent = 'Add Skill';
            this.skillNameInput.value = '';
            this.skillContentInput.value = '';
            this.deleteSkillBtn.hidden = true;
        }
        
        this.skillModal.classList.add('active');
        this.skillNameInput.focus();
    }

    closeSkillModal() {
        this.skillModal.classList.remove('active');
        this.editingSkillIndex = null;
    }

    saveSkill() {
        const name = this.skillNameInput.value.trim();
        const content = this.skillContentInput.value.trim();
        
        if (!name || !content) {
            alert('Please fill in both name and content');
            return;
        }
        
        if (this.editingSkillIndex !== null) {
            this.skills[this.editingSkillIndex].name = name;
            this.skills[this.editingSkillIndex].content = content;
        } else {
            this.skills.push({ name, content, enabled: true });
        }
        
        this.renderSkills();
        this.updateContextMeter();
        this.saveToStorage();
        this.closeSkillModal();
    }

    deleteSkill() {
        if (this.editingSkillIndex !== null) {
            this.skills.splice(this.editingSkillIndex, 1);
            this.renderSkills();
            this.updateContextMeter();
            this.saveToStorage();
            this.closeSkillModal();
        }
    }

    // Drag and drop
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        this.dropOverlay.classList.add('active');
    }

    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget)) {
            this.dropOverlay.classList.remove('active');
        }
    }

    async handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.dropOverlay.classList.remove('active');
        
        const files = Array.from(e.dataTransfer.files);
        const textFiles = files.filter(f => 
            f.type.startsWith('text/') || 
            f.name.endsWith('.txt') || 
            f.name.endsWith('.md') ||
            f.name.endsWith('.json') ||
            f.name.endsWith('.js') ||
            f.name.endsWith('.py') ||
            f.name.endsWith('.c') ||
            f.name.endsWith('.h') ||
            f.name.endsWith('.sql') ||
            f.name.endsWith('.xml') ||
            f.name.endsWith('.yaml') ||
            f.name.endsWith('.yml') ||
            f.name.endsWith('.sh') ||
            f.name.endsWith('.css') ||
            f.name.endsWith('.html')
        );
        
        for (const file of textFiles) {
            try {
                const content = await this.readFile(file);
                const contextMessage = `[File: ${file.name}]\n\`\`\`\n${content}\n\`\`\``;
                
                // Add to current input or create file context
                if (this.userInput.value) {
                    this.userInput.value += '\n\n' + contextMessage;
                } else {
                    this.userInput.value = contextMessage;
                }
                
                this.autoResizeTextarea();
                this.updateContextMeter();
            } catch (err) {
                console.error('Error reading file:', err);
            }
        }
    }

    readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsText(file);
        });
    }

    // Chat functionality
    async sendMessage() {
        const content = this.userInput.value.trim();
        if (!content || this.isStreaming) return;
        
        const endpoint = this.apiEndpointInput.value.trim();
        const model = this.modelNameInput.value.trim();
        
        if (!endpoint || !model) {
            alert('Please configure API endpoint and model in the sidebar');
            return;
        }
        
        // Add user message
        this.messages.push({ role: 'user', content });
        this.renderMessage({ role: 'user', content });
        
        // Clear input
        this.userInput.value = '';
        this.autoResizeTextarea();
        
        // Hide welcome message
        const welcome = this.chatMessages.querySelector('.welcome-message');
        if (welcome) welcome.remove();
        
        // Prepare request
        const systemPrompt = this.buildSystemPrompt();
        const requestMessages = systemPrompt 
            ? [{ role: 'system', content: systemPrompt }, ...this.messages]
            : this.messages;
        
        const requestBody = {
            model,
            messages: requestMessages,
            stream: true
        };
        
        // Add reasoning parameters if enabled
        if (this.enableReasoningCheckbox.checked) {
            const budget = parseInt(this.reasoningBudgetInput.value) || 4096;
            // OpenAI-style reasoning parameters
            requestBody.reasoning_effort = 'high';
            requestBody.max_completion_tokens = budget + 4096; // thinking + response
        }
        
        // Create assistant message placeholder
        const assistantMessage = { role: 'assistant', content: '', thinking: '' };
        this.messages.push(assistantMessage);
        const messageEl = this.renderMessage(assistantMessage, true);
        
        // Start streaming
        this.isStreaming = true;
        this.sendBtn.hidden = true;
        this.stopBtn.hidden = false;
        this.abortController = new AbortController();
        
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody),
                signal: this.abortController.signal
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            await this.handleStream(response, assistantMessage, messageEl);
            
        } catch (err) {
            if (err.name === 'AbortError') {
                assistantMessage.content += '\n\n*[Generation stopped]*';
            } else {
                assistantMessage.content = `Error: ${err.message}`;
            }
            this.updateMessageContent(messageEl, assistantMessage);
        } finally {
            this.isStreaming = false;
            this.sendBtn.hidden = false;
            this.stopBtn.hidden = true;
            this.abortController = null;
            this.updateContextMeter();
            this.saveToStorage();
            
            // Remove streaming indicator
            const indicator = messageEl.querySelector('.streaming-indicator');
            if (indicator) indicator.remove();
        }
    }

    async handleStream(response, message, messageEl) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        // Track whether we're in thinking or answer mode
        let inThinking = false;
        let inAnswer = false;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') continue;
                    
                    try {
                        const parsed = JSON.parse(data);
                        const delta = parsed.choices?.[0]?.delta;
                        
                        if (delta) {
                            // Handle reasoning_content (OpenAI style)
                            if (delta.reasoning_content) {
                                message.thinking += delta.reasoning_content;
                            }
                            
                            // Handle regular content
                            if (delta.content) {
                                let content = delta.content;
                                
                                // Check for <thinking> and <answer> tags
                                if (content.includes('<thinking>')) {
                                    inThinking = true;
                                    content = content.replace('<thinking>', '');
                                }
                                if (content.includes('</thinking>')) {
                                    inThinking = false;
                                    content = content.replace('</thinking>', '');
                                }
                                if (content.includes('<answer>')) {
                                    inAnswer = true;
                                    content = content.replace('<answer>', '');
                                }
                                if (content.includes('</answer>')) {
                                    inAnswer = false;
                                    content = content.replace('</answer>', '');
                                }
                                
                                if (inThinking) {
                                    message.thinking += content;
                                } else {
                                    message.content += content;
                                }
                            }
                            
                            this.updateMessageContent(messageEl, message);
                        }
                    } catch (e) {
                        // Ignore parse errors for malformed chunks
                    }
                }
            }
        }
    }

    stopGeneration() {
        if (this.abortController) {
            this.abortController.abort();
        }
    }

    buildSystemPrompt() {
        let prompt = this.systemPromptInput.value || '';
        
        // Add enabled skills
        const enabledSkills = this.skills.filter(s => s.enabled);
        if (enabledSkills.length > 0) {
            if (prompt) prompt += '\n\n';
            prompt += '--- Additional Context ---\n\n';
            enabledSkills.forEach(skill => {
                prompt += `### ${skill.name}\n${skill.content}\n\n`;
            });
        }
        
        return prompt;
    }

    renderMessage(message, isStreaming = false) {
        const div = document.createElement('div');
        div.className = `message ${message.role}`;
        
        // Thinking block for assistant
        if (message.role === 'assistant') {
            const thinkingBlock = document.createElement('div');
            thinkingBlock.className = 'thinking-block collapsed';
            thinkingBlock.innerHTML = `
                <div class="thinking-header">
                    <span class="thinking-label">Thinking</span>
                    <span class="thinking-toggle">▼</span>
                </div>
                <div class="thinking-content"></div>
            `;
            thinkingBlock.querySelector('.thinking-header').addEventListener('click', () => {
                thinkingBlock.classList.toggle('collapsed');
            });
            
            // Only show if there's thinking content
            thinkingBlock.style.display = message.thinking ? 'block' : 'none';
            div.appendChild(thinkingBlock);
        }
        
        // Message bubble
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        bubble.appendChild(content);
        
        if (isStreaming) {
            const indicator = document.createElement('span');
            indicator.className = 'streaming-indicator';
            bubble.appendChild(indicator);
        }
        
        div.appendChild(bubble);
        
        // Actions
        const actions = document.createElement('div');
        actions.className = 'message-actions';
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'message-action-btn';
        copyBtn.textContent = 'Copy';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(message.content);
            copyBtn.textContent = 'Copied!';
            setTimeout(() => copyBtn.textContent = 'Copy', 1500);
        });
        actions.appendChild(copyBtn);
        
        div.appendChild(actions);
        
        this.chatMessages.appendChild(div);
        this.updateMessageContent(div, message);
        this.scrollToBottom();
        
        return div;
    }

    updateMessageContent(element, message) {
        const contentEl = element.querySelector('.message-content');
        const thinkingBlock = element.querySelector('.thinking-block');
        const thinkingContent = element.querySelector('.thinking-content');
        
        // Update thinking block
        if (thinkingBlock && thinkingContent) {
            if (message.thinking) {
                thinkingBlock.style.display = 'block';
                thinkingContent.innerHTML = this.renderMarkdown(message.thinking);
            } else {
                thinkingBlock.style.display = 'none';
            }
        }
        
        // Update main content
        if (message.role === 'user') {
            contentEl.innerHTML = this.renderMarkdown(message.content);
        } else {
            contentEl.innerHTML = this.renderMarkdown(message.content) || '<span class="text-muted">...</span>';
        }
        
        // Highlight code blocks
        element.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
        
        this.scrollToBottom();
    }

    renderMarkdown(text) {
        if (!text) return '';
        
        // Configure marked
        marked.setOptions({
            breaks: true,
            gfm: true
        });
        
        return marked.parse(text);
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    // Import/Export
    exportConversation() {
        const data = {
            version: 1,
            exportedAt: new Date().toISOString(),
            config: {
                apiEndpoint: this.apiEndpointInput.value,
                model: this.modelNameInput.value,
                enableReasoning: this.enableReasoningCheckbox.checked,
                reasoningBudget: parseInt(this.reasoningBudgetInput.value),
                systemPrompt: this.systemPromptInput.value,
                maxContextTokens: parseInt(this.maxContextTokensInput.value)
            },
            skills: this.skills,
            messages: this.messages
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `llm-chat-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        
        URL.revokeObjectURL(url);
    }

    importConversation(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = JSON.parse(e.target.result);
                
                if (data.config) {
                    this.apiEndpointInput.value = data.config.apiEndpoint || '';
                    this.modelNameInput.value = data.config.model || '';
                    this.enableReasoningCheckbox.checked = data.config.enableReasoning || false;
                    this.reasoningBudgetInput.value = data.config.reasoningBudget || 4096;
                    this.systemPromptInput.value = data.config.systemPrompt || '';
                    this.maxContextTokensInput.value = data.config.maxContextTokens || 128000;
                    
                    this.toggleReasoningBudget();
                    this.updateModelDisplay();
                }
                
                if (data.skills) {
                    this.skills = data.skills;
                    this.renderSkills();
                }
                
                if (data.messages) {
                    this.messages = data.messages;
                    this.renderAllMessages();
                }
                
                this.updateContextMeter();
                this.saveToStorage();
                
            } catch (err) {
                alert('Error importing conversation: ' + err.message);
            }
        };
        reader.readAsText(file);
        
        // Reset file input
        event.target.value = '';
    }

    clearConversation() {
        if (!confirm('Are you sure you want to clear the conversation?')) return;
        
        this.messages = [];
        this.chatMessages.innerHTML = `
            <div class="welcome-message">
                <p>Configure your API endpoint in the sidebar to get started.</p>
                <p class="hint">Drag and drop text files here to add context, or use the sidebar to configure skills.</p>
            </div>
        `;
        this.updateContextMeter();
        this.saveToStorage();
    }

    renderAllMessages() {
        this.chatMessages.innerHTML = '';
        
        if (this.messages.length === 0) {
            this.chatMessages.innerHTML = `
                <div class="welcome-message">
                    <p>Configure your API endpoint in the sidebar to get started.</p>
                    <p class="hint">Drag and drop text files here to add context, or use the sidebar to configure skills.</p>
                </div>
            `;
            return;
        }
        
        this.messages.forEach(msg => this.renderMessage(msg));
    }

    // Storage
    saveToStorage() {
        const data = {
            config: {
                apiEndpoint: this.apiEndpointInput.value,
                model: this.modelNameInput.value,
                enableReasoning: this.enableReasoningCheckbox.checked,
                reasoningBudget: parseInt(this.reasoningBudgetInput.value),
                systemPrompt: this.systemPromptInput.value,
                maxContextTokens: parseInt(this.maxContextTokensInput.value)
            },
            skills: this.skills,
            messages: this.messages
        };
        
        localStorage.setItem('llm-chat-data', JSON.stringify(data));
    }

    loadFromStorage() {
        const saved = localStorage.getItem('llm-chat-data');
        if (!saved) return;
        
        try {
            const data = JSON.parse(saved);
            
            if (data.config) {
                this.apiEndpointInput.value = data.config.apiEndpoint || '';
                this.modelNameInput.value = data.config.model || '';
                this.enableReasoningCheckbox.checked = data.config.enableReasoning || false;
                this.reasoningBudgetInput.value = data.config.reasoningBudget || 4096;
                this.systemPromptInput.value = data.config.systemPrompt || '';
                this.maxContextTokensInput.value = data.config.maxContextTokens || 128000;
                
                this.toggleReasoningBudget();
                this.updateModelDisplay();
            }
            
            if (data.skills) {
                this.skills = data.skills;
                this.renderSkills();
            }
            
            if (data.messages) {
                this.messages = data.messages;
                this.renderAllMessages();
            }
            
        } catch (err) {
            console.error('Error loading from storage:', err);
        }
    }

    // Utilities
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.app = new LLMChat();
});
