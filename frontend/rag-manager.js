/* RAG 知识库管理界面 JavaScript */

(function() {
    'use strict';

    // ==================== 工具函数 ====================

    function showMessage(elementId, message, type = 'success') {
        const msgEl = document.getElementById(elementId);
        msgEl.innerHTML = `<div class="message ${type}">${message}</div>`;
        setTimeout(() => {
            msgEl.innerHTML = '';
        }, 5000);
    }

    function showLoading(elementId) {
        const el = document.getElementById(elementId);
        el.innerHTML = '<div class="loading"><div class="spinner"></div><p>加载中...</p></div>';
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }

    // ==================== 标签页切换 ====================

    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.dataset.tab;

            // 切换标签样式
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // 切换内容
            tabContents.forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(targetTab).classList.add('active');

            // 如果切换到概览，刷新统计
            if (targetTab === 'overview') {
                loadStats();
            }
        });
    });

    // ==================== 加载统计信息 ====================

    async function loadStats() {
        try {
            const response = await fetch('/api/rag/stats');
            const data = await response.json();

            if (data.success) {
                document.getElementById('stat-docs').textContent = data.total_documents;
                document.getElementById('stat-chunks').textContent = data.total_chunks;
                document.getElementById('stat-categories').textContent = Object.keys(data.categories).length;

                // 显示分类列表
                const categoriesList = document.getElementById('categories-list');
                if (Object.keys(data.categories).length > 0) {
                    let html = '<div style="display: grid; gap: 12px;">';
                    for (const [category, count] of Object.entries(data.categories)) {
                        html += `
                            <div style="display: flex; justify-content: space-between; padding: 12px; background: var(--raised); border-radius: 5px;">
                                <span>${getCategoryName(category)}</span>
                                <span style="color: var(--gold); font-weight: 500;">${count} 块</span>
                            </div>
                        `;
                    }
                    html += '</div>';
                    categoriesList.innerHTML = html;
                } else {
                    categoriesList.innerHTML = '<p style="color: var(--muted); text-align: center;">暂无数据</p>';
                }
            }
        } catch (error) {
            console.error('加载统计失败:', error);
        }
    }

    function getCategoryName(key) {
        const names = {
            'stock_report': '股票研报',
            'financial_report': '财务报告',
            'announcement': '公司公告',
            'industry_research': '行业研究',
            'investment_book': '投资书籍',
            'tutorial': '教程文档',
            'other': '其他',
            'unknown': '未分类'
        };
        return names[key] || key;
    }

    // ==================== 文件上传 ====================

    const fileUploadArea = document.getElementById('file-upload-area');
    const fileInput = document.getElementById('file-input');
    const uploadBtn = document.getElementById('upload-btn');
    let selectedFile = null;

    // 点击区域触发文件选择
    fileUploadArea.addEventListener('click', () => {
        fileInput.click();
    });

    // 文件选择
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // 拖拽上传
    fileUploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileUploadArea.classList.add('dragover');
    });

    fileUploadArea.addEventListener('dragleave', () => {
        fileUploadArea.classList.remove('dragover');
    });

    fileUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        fileUploadArea.classList.remove('dragover');

        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    function handleFileSelect(file) {
        selectedFile = file;

        // 显示文件信息
        document.getElementById('filename').textContent = file.name;
        document.getElementById('filesize').textContent = formatFileSize(file.size);
        document.getElementById('file-info').style.display = 'block';

        // 启用上传按钮
        uploadBtn.disabled = false;
    }

    // 上传文件
    uploadBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        uploadBtn.disabled = true;
        uploadBtn.textContent = '上传中...';

        try {
            const formData = new FormData();
            formData.append('file', selectedFile);

            const category = document.getElementById('upload-category').value;
            const source = document.getElementById('upload-source').value;
            const stockCode = document.getElementById('upload-stock').value;

            if (category) formData.append('category', category);
            if (source) formData.append('source', source);
            if (stockCode) formData.append('stock_code', stockCode);

            const response = await fetch('/api/rag/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                showMessage('upload-message', `上传成功！已添加 ${result.chunks} 个文档块`, 'success');

                // 重置表单
                selectedFile = null;
                fileInput.value = '';
                document.getElementById('file-info').style.display = 'none';
                document.getElementById('upload-category').value = '';
                document.getElementById('upload-source').value = '';
                document.getElementById('upload-stock').value = '';
            } else {
                showMessage('upload-message', `上传失败: ${result.message}`, 'error');
            }
        } catch (error) {
            showMessage('upload-message', `上传失败: ${error.message}`, 'error');
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = '上传到知识库';
        }
    });

    // ==================== 搜索功能 ====================

    const searchBtn = document.getElementById('search-btn');
    const searchQuery = document.getElementById('search-query');

    searchBtn.addEventListener('click', performSearch);
    searchQuery.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    async function performSearch() {
        const query = searchQuery.value.trim();
        if (!query) {
            showMessage('search-message', '请输入搜索内容', 'error');
            return;
        }

        const resultsEl = document.getElementById('search-results');
        showLoading('search-results');

        try {
            const limit = parseInt(document.getElementById('search-limit').value);

            const response = await fetch('/api/rag/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    query: query,
                    n_results: limit
                })
            });

            const data = await response.json();

            if (data.success) {
                if (data.results.length === 0) {
                    resultsEl.innerHTML = '<p style="color: var(--muted); text-align: center; padding: 40px;">未找到相关结果</p>';
                } else {
                    let html = '';
                    data.results.forEach((item, index) => {
                        const similarity = Number.isFinite(item.similarity)
                            && item.similarity >= -1 && item.similarity <= 1
                            ? `${(item.similarity * 100).toFixed(1)}%` : '未知';
                        html += `
                            <div class="result-item">
                                <div class="result-text">${item.text}</div>
                                <div class="result-meta">
                                    <span class="similarity">余弦相似度: ${similarity}</span>
                                    ${item.metadata.filename ? `<span>文件: ${item.metadata.filename}</span>` : ''}
                                    ${item.metadata.stock_code ? `<span>股票: ${item.metadata.stock_code}</span>` : ''}
                                    ${item.metadata.category ? `<span>分类: ${getCategoryName(item.metadata.category)}</span>` : ''}
                                </div>
                            </div>
                        `;
                    });
                    resultsEl.innerHTML = html;
                }
            } else {
                resultsEl.innerHTML = `<p style="color: var(--red); text-align: center;">搜索失败: ${data.message}</p>`;
            }
        } catch (error) {
            resultsEl.innerHTML = `<p style="color: var(--red); text-align: center;">搜索失败: ${error.message}</p>`;
        }
    }

    // ==================== 添加文本 ====================

    const addTextBtn = document.getElementById('add-text-btn');

    addTextBtn.addEventListener('click', async () => {
        const content = document.getElementById('text-content').value.trim();

        if (!content) {
            showMessage('text-message', '请输入文本内容', 'error');
            return;
        }

        addTextBtn.disabled = true;
        addTextBtn.textContent = '添加中...';

        try {
            const category = document.getElementById('text-category').value;
            const stockCode = document.getElementById('text-stock').value;

            const metadata = {};
            if (category) metadata.category = category;
            if (stockCode) metadata.stock_code = stockCode;
            metadata.source = 'manual';

            const response = await fetch('/api/rag/add-text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: content,
                    metadata: metadata
                })
            });

            const result = await response.json();

            if (result.success) {
                showMessage('text-message', `添加成功！已添加 ${result.chunks} 个文档块`, 'success');

                // 重置表单
                document.getElementById('text-content').value = '';
                document.getElementById('text-category').value = '';
                document.getElementById('text-stock').value = '';
            } else {
                showMessage('text-message', `添加失败: ${result.message}`, 'error');
            }
        } catch (error) {
            showMessage('text-message', `添加失败: ${error.message}`, 'error');
        } finally {
            addTextBtn.disabled = false;
            addTextBtn.textContent = '添加到知识库';
        }
    });

    // ==================== 初始化 ====================

    // 页面加载时加载统计
    loadStats();
})();
