// ESG Knowledge Graph Visualization using D3.js

let svg, g, simulation, zoom;
let nodes = [], links = [];
const PAGE_PARAMS = new URLSearchParams(window.location.search);
const DOCUMENT_ID = PAGE_PARAMS.get('document_id') || '';
const API_PREFIX = '/kg-api';
let currentFilters = {
    years: [],
    companies: [],
    esg_domains: [],
    limit: 1000
};
let nodeInfoLocked = false; // 跟踪节点信息面板是否被锁定显示
let edgeInfoLocked = false; // 跟踪边信息面板是否被锁定显示

// 初始化图表
function initGraph() {
    syncPanelHeights();
    const width = document.getElementById('graph-container').clientWidth;
    const height = getCanvasHeight();

    // 创建SVG
    svg = d3.select('#graph-container')
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .style('touch-action', 'manipulation') // 启用触摸手势
        .style('user-select', 'none'); // 防止文本选择

    // 添加缩放和平移
    zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', function(event) {
            g.attr('transform', event.transform);
        });

    svg.call(zoom)
        .on('dblclick.zoom', null); // 禁用双击缩放，避免与节点点击冲突

    // 创建主容器组
    g = svg.append('g');

    // 添加箭头标记
    svg.append('defs').selectAll('marker')
        .data(['end'])
        .enter().append('marker')
        .attr('id', d => d)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 25)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#999');

    // 创建力导向图模拟
    simulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 5));

    // 加载初始数据
    renderViewContext();
    loadFilters();
    loadGraphData();
}

function buildApiUrl(path, params = new URLSearchParams()) {
    if (DOCUMENT_ID) {
        params.set('document_id', DOCUMENT_ID);
    }
    return `${API_PREFIX}${path}?${params.toString()}`;
}

function renderViewContext() {
    const el = document.getElementById('view-context');
    if (!el) return;
    el.textContent = DOCUMENT_ID
        ? `Scoped to current report: ${DOCUMENT_ID}`
        : 'Showing the broader ESG graph across indexed reports.';
}

// 获取节点半径
function getNodeRadius(d) {
    const baseRadius = {
        'esg_initiative': 8,
        'esg_metric': 6,
        'outcome': 7,
        'risk_factor': 5
    };
    return baseRadius[d.type] || 6;
}

// 获取节点颜色
function getNodeColor(d) {
    const colors = {
        'environmental': '#28a745',
        'social': '#007bff',
        'governance': '#6f42c1'
    };
    if (d.type === 'risk_factor') return '#dc3545';
    return colors[d.esg_domain] || '#6c757d';
}

// 加载筛选选项
function loadFilters() {
    const params = new URLSearchParams();
    return fetch(buildApiUrl('/filters', params))
        .then(response => response.json())
        .then(data => {
            populateFilters('year-filters', data.years, 'years');
            populateCompanies(data.companies);
            populateFilters('domain-filters', data.esg_domains, 'esg_domains');

            currentFilters.years = [...data.years];
            currentFilters.companies = DOCUMENT_ID && data.companies.length === 1 ? [data.companies[0]] : [];
            currentFilters.esg_domains = [...data.esg_domains];
            updateFilterCheckboxes();
            if (typeof window.refreshFilterToggleStates === "function") {
                window.refreshFilterToggleStates();
            }
            setTimeout(syncPanelHeights, 0);
        })
        .catch(error => {
            console.error('Error loading filters:', error);
        });
}


const COMPANY_DEFAULTS = ['Apple', 'Nvidia'];

function populateCompanies(options = []) {
    const select = document.getElementById('company-select');
    if (!select) return;
    const pool = DOCUMENT_ID
        ? Array.from(new Set(options))
        : Array.from(new Set([...options, ...COMPANY_DEFAULTS]));
    select.innerHTML = '<option value="">Select a company</option>';
    pool.forEach(company => {
        if (!company) return;
        const option = document.createElement('option');
        option.value = company;
        option.textContent = company;
        select.appendChild(option);
    });
    const current = currentFilters.companies && currentFilters.companies[0];
    select.value = current || '';
    select.disabled = Boolean(DOCUMENT_ID && pool.length <= 1);
    if (!select.dataset.bound) {
        select.addEventListener('change', () => {
            updateCurrentFilters();
        });
        select.dataset.bound = 'true';
    }
}

function getCompanyValue() {
    const select = document.getElementById('company-select');
    if (!select) return [];
    const value = select.value;
    return value ? [value] : [];
}
const FILTER_OPTION_ICONS = {
    esg_domains: {
        environmental: '<i class=\"fas fa-leaf\"></i>',
        financial: '<i class=\"fas fa-dollar-sign\"></i>',
        governance: '<i class=\"fas fa-university\"></i>',
        social: '<i class=\"fas fa-users\"></i>'
    }
};

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function safeValue(value) {
    if (value === null || value === undefined || value === '') {
        return '—';
    }
    return escapeHtml(value);
}

function uppercaseValue(value) {
    return safeValue(value).toUpperCase();
}


function populateFilters(containerId, options, filterType) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    options.forEach(option => {
        const div = document.createElement('div');
        div.className = 'form-check';

        const optionId = `${filterType}_${option}`.replace(/\s+/g, '_');

        const input = document.createElement('input');
        input.className = 'form-check-input';
        input.type = 'checkbox';
        input.id = optionId;
        input.value = option;
        const shouldCheck = filterType !== 'companies';
        input.checked = shouldCheck;

        const label = document.createElement('label');
        label.className = 'form-check-label';
        label.htmlFor = optionId;

        const iconKey = option.toString().toLowerCase();
        const iconHtml = FILTER_OPTION_ICONS[filterType]?.[iconKey] || '';
        label.innerHTML = `${iconHtml ? `<span class=\"filter-option-icon\">${iconHtml}</span>` : ''}<span class=\"filter-option-text\">${option}</span>`;

        div.appendChild(input);
        div.appendChild(label);
        container.appendChild(div);

        updateFilterRowHighlight(input);

        input.addEventListener('change', () => {
            updateFilterRowHighlight(input);
            updateCurrentFilters();
        });

        div.addEventListener('click', event => {
            if (event.target === input || event.target.tagName === 'LABEL' || event.target.closest('label')) {
                return;
            }
            input.checked = !input.checked;
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });
    });

    if (typeof window.refreshFilterToggleStates === 'function') {
        window.refreshFilterToggleStates();
    }
}

function updateFilterRowHighlight(input) {
    const row = input.closest('.form-check');
    if (!row) return;
    row.classList.toggle('is-checked', input.checked);
}

function refreshFilterHighlights() {
    ['year-filters', 'domain-filters'].forEach(id => {
        const container = document.getElementById(id);
        if (!container) return;
        container.querySelectorAll('input[type="checkbox"]').forEach(updateFilterRowHighlight);
    });
}

function updateCurrentFilters() {
    currentFilters.years = getCheckedValues('year-filters');
    currentFilters.companies = getCompanyValue();
    currentFilters.esg_domains = getCheckedValues('domain-filters');
    currentFilters.limit = parseInt(document.getElementById('node-limit').value);
    document.getElementById('limit-value').textContent = currentFilters.limit;
    refreshFilterHighlights();
    if (typeof window.refreshFilterToggleStates === "function") {
        window.refreshFilterToggleStates();
    }
}

function getCheckedValues(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

function updateFilterCheckboxes() {
    ['years', 'esg_domains'].forEach(key => {
        const containerId = `${key}-filters`;
        const container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.checked = currentFilters[key].includes(cb.value);
            updateFilterRowHighlight(cb);
        });
    });
    const companySelect = document.getElementById('company-select');
    if (companySelect) {
        companySelect.value = currentFilters.companies[0] || '';
    }
    if (typeof window.refreshFilterToggleStates === "function") {
        window.refreshFilterToggleStates();
    }
}

// 加载图表数据
function loadGraphData() {
    showLoading();

    const params = new URLSearchParams();
    currentFilters.years.forEach(year => params.append('years', year));
    currentFilters.companies.forEach(company => params.append('companies', company));
    currentFilters.esg_domains.forEach(domain => params.append('esg_domains', domain));
    params.append('limit', currentFilters.limit);

    fetch(buildApiUrl('/graph', params))
        .then(response => response.json())
        .then(data => {
            nodes = data.nodes;
            links = data.edges;
            renderGraph();
            hideLoading();
        })
        .catch(error => {
            console.error('Error loading graph data:', error);
            hideLoading();
        });
}

// 渲染图表
function renderGraph() {
    // 重置信息面板锁定状态（避免切换筛选时状态混乱）
    nodeInfoLocked = false;
    edgeInfoLocked = false;
    hideNodeInfo();
    hideEdgeInfo();

    // 清除现有元素
    g.selectAll('*').remove();

    // 创建边
    const link = g.selectAll('.link')
        .data(links)
        .enter().append('line')
        .attr('class', 'link')
        .attr('marker-end', 'url(#end)')
        .style('cursor', 'pointer')
        .on('click', function(event, d) {
            showEdgeInfo(event, d, true);
        });

    // Edge labels
    const linkLabels = g.selectAll('.link-label')
        .data(links)
        .enter()
        .append('text')
        .attr('class', 'link-label')
        .attr('fill', '#2f855a')
        .attr('font-weight', '600')
        .attr('stroke', '#ffffff')
        .attr('stroke-width', 3)
        .style('paint-order', 'stroke')
        .style('font-size', '11px')
        .style('pointer-events', 'none')
        .attr('text-anchor', 'middle')
        .text(d => d.relationship_type || d.type || '');

    // 创建节点组
    const node = g.selectAll('.node')
        .data(nodes)
        .enter().append('g')
        .attr('class', 'node')
        .style('cursor', 'pointer')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended))
        .on('click', function(event, d) {
            showNodeInfo(event, d, true); // 第三个参数表示点击保持显示
            highlightConnections(event, d);
        });

    // 添加节点圆圈
    node.append('circle')
        .attr('r', d => getNodeRadius(d))
        .attr('fill', d => getNodeColor(d))
        .attr('class', d => `node ${d.esg_domain} ${d.type}`);

    // 添加节点标签
    node.append('text')
        .attr('class', 'node-label')
        .attr('dy', '-1em')
        .attr('fill', '#000000')
        .attr('font-weight', '600')
        .attr('stroke', '#ffffff')
        .attr('stroke-width', 3)
        .attr('stroke-linejoin', 'round')
        .style('paint-order', 'stroke')
        .style('font-size', '12px')
        .text(d => d.label);

    // 更新力导向图
    simulation
        .nodes(nodes)
        .on('tick', ticked);

    simulation.force('link')
        .links(links);

    simulation.alpha(1).restart();
    setTimeout(syncPanelHeights, 0);

    function ticked() {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        linkLabels
            .attr('x', d => {
                const midX = (d.source.x + d.target.x) / 2;
                const dx = d.target.x - d.source.x;
                const dy = d.target.y - d.source.y;
                const len = Math.sqrt(dx * dx + dy * dy) || 1;
                const offset = 22;
                const nx = -dy / len;
                return midX + nx * offset;
            })
            .attr('y', d => {
                const midY = (d.source.y + d.target.y) / 2;
                const dx = d.target.x - d.source.x;
                const dy = d.target.y - d.source.y;
                const len = Math.sqrt(dx * dx + dy * dy) || 1;
                const offset = 22;
                const ny = dx / len;
                return midY + ny * offset;
            });

        node
            .attr('transform', d => `translate(${d.x},${d.y})`);
    }
}

// 拖拽功能
function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// 显示节点信息 - 优化性能版本
function showNodeInfo(event, d, keepVisible = false) {
    const panel = document.getElementById('node-info-panel');
    const content = document.getElementById('node-info-content');
    const edgePanel = document.getElementById('edge-info-panel');
    if (edgePanel) {
        edgePanel.style.display = 'none';
        edgeInfoLocked = false;
        document.removeEventListener('click', hideEdgeInfoOnClickOutside);
    }

    // 使用更高效的DOM操作
    const infoHtml = `
        <div class="info-item">
            <span class="info-label">Name:</span>
            <span class="info-value">${d.label}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Type:</span>
            <span class="info-value">${d.type}</span>
        </div>
        <div class="info-item">
            <span class="info-label">ESG Domain:</span>
            <span class="info-value">${d.esg_domain}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Year:</span>
            <span class="info-value">${d.year}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Company:</span>
            <span class="info-value">${d.company}</span>
        </div>
        <div class="info-item">
            <span class="info-label">Frequency:</span>
            <span class="info-value">${d.frequency}</span>
        </div>
            `;

    // 一次性更新DOM
    content.innerHTML = infoHtml;
    panel.style.display = 'block';

    // 如果是点击保持显示，设置锁定状态并添加全局点击事件监听器
    if (keepVisible) {
        nodeInfoLocked = true;
        // 移除之前的监听器
        document.removeEventListener('click', hideNodeInfoOnClickOutside);

        // 添加新的监听器
        setTimeout(() => {
            document.addEventListener('click', hideNodeInfoOnClickOutside);
        }, 10);
    }
}

// 点击外部区域关闭节点信息
function hideNodeInfoOnClickOutside(event) {
    const panel = document.getElementById('node-info-panel');
    const graphContainer = document.getElementById('graph-container');

    // 如果点击的不是面板内部或图表区域，隐藏面板
    if (!panel.contains(event.target) && !graphContainer.contains(event.target)) {
        hideNodeInfo();
        nodeInfoLocked = false; // 重置锁定状态
        document.removeEventListener('click', hideNodeInfoOnClickOutside);
    }
}

// 隐藏节点信息
function hideNodeInfo() {
    document.getElementById('node-info-panel').style.display = 'none';
}

// 显示边信息 - 优化性能版本
function showEdgeInfo(event, d, keepVisible = false) {
    const panel = document.getElementById('edge-info-panel');
    const content = document.getElementById('edge-info-content');
    const nodePanel = document.getElementById('node-info-panel');
    if (nodePanel) {
        nodePanel.style.display = 'none';
        nodeInfoLocked = false;
        document.removeEventListener('click', hideNodeInfoOnClickOutside);
    }
    if (!panel || !content) return;

    const sourceId = getNodeId(d.source);
    const targetId = getNodeId(d.target);

    highlightEdgeSelection(d);

    const sourceNode = nodes.find(n => n.id === sourceId);
    const targetNode = nodes.find(n => n.id === targetId);

    const buildRow = (label, value) => `
        <div class="edge-detail-card__row">
            <span class="edge-detail-card__label">${escapeHtml(label)}</span>
            <span class="edge-detail-card__value">${safeValue(value)}</span>
        </div>
    `;

    const buildCard = (variant, icon, title, rows, extra = '') => `
        <div class="edge-detail-card ${variant}">
            <div class="edge-detail-card__title"><i class="fas ${icon}"></i><span>${escapeHtml(title.toUpperCase())}</span></div>
            <div class="edge-detail-card__rows">${rows}</div>
            ${extra}
        </div>
    `;

    const buildNodeCard = (title, node, variant, icon) => {
        if (!node) {
            return buildCard('edge-detail-card--empty', 'fa-circle', title, `<div class="edge-detail-card__placeholder text-muted">No ${title.toLowerCase()} data.</div>`);
        }
        const rows = [
            buildRow('Name', node.label),
            buildRow('Type', uppercaseValue(node.type)),
            buildRow('Domain', node.esg_domain),
            buildRow('Year', node.year),
            buildRow('Company', node.company)
        ].join('');
        return buildCard(variant, icon, title, rows);
    };

    const relationshipRows = [
        buildRow('Type', uppercaseValue(d.type)),
        buildRow('Nature', uppercaseValue(d.relationship_nature || 'UNKNOWN')),
        buildRow('Action', uppercaseValue(d.relationship_action || 'UNKNOWN'))
    ].join('');

    const evidenceBlock = d.evidence ? `
        <div class="edge-detail-card__evidence">
            <span class="edge-detail-card__label edge-detail-card__label--inline">Evidence</span>
            <p class="edge-detail-card__evidence-text">${safeValue(d.evidence)}</p>
        </div>
    ` : '';

    const relationshipCard = buildCard('edge-detail-card--relationship', 'fa-link', 'Relationship', relationshipRows, evidenceBlock);

    content.innerHTML = `
        <div class="edge-inspector__column">${buildNodeCard('Source Node', sourceNode, 'edge-detail-card--source', 'fa-location-arrow')}</div>
        <div class="edge-inspector__column">${relationshipCard}</div>
        <div class="edge-inspector__column">${buildNodeCard('Target Node', targetNode, 'edge-detail-card--target', 'fa-bullseye')}</div>
    `;

    panel.style.display = 'block';

    if (keepVisible) {
        edgeInfoLocked = true;
        document.removeEventListener('click', hideEdgeInfoOnClickOutside);
        setTimeout(() => {
            document.addEventListener('click', hideEdgeInfoOnClickOutside);
        }, 10);
    }
}

// 点击外部区域关闭边信息
function hideEdgeInfoOnClickOutside(event) {
    const panel = document.getElementById('edge-info-panel');
    const graphContainer = document.getElementById('graph-container');

    // 如果点击的不是面板内部或图表区域，隐藏面板
    if (!panel.contains(event.target) && !graphContainer.contains(event.target)) {
        hideEdgeInfo();
        edgeInfoLocked = false; // 重置锁定状态
        document.removeEventListener('click', hideEdgeInfoOnClickOutside);
    }
}

// 隐藏边信息
function hideEdgeInfo() {
    document.getElementById('edge-info-panel').style.display = 'none';
    d3.selectAll('.link').classed('highlighted-link', false);
    d3.selectAll('.node circle').classed('highlighted', false);
}

function getNodeId(ref) {
    if (!ref) return undefined;
    return typeof ref === 'object' ? ref.id || ref : ref;
}

function highlightEdgeSelection(edge) {
    const sourceId = getNodeId(edge.source);
    const targetId = getNodeId(edge.target);

    d3.selectAll('.node circle').classed('highlighted', false);
    d3.selectAll('.link').classed('highlighted-link', false);

    d3.selectAll('.node')
        .filter(n => n.id === sourceId || n.id === targetId)
        .select('circle')
        .classed('highlighted', true);

    d3.selectAll('.link')
        .filter(l => getNodeId(l.source) === sourceId && getNodeId(l.target) === targetId && l.id === edge.id)
        .classed('highlighted-link', true);
}

// 高亮连接
function highlightConnections(event, d) {
    // 清除现有高亮
    d3.selectAll('.node circle').classed('highlighted', false);
    d3.selectAll('.link').classed('highlighted-link', false);

    // 高亮选中的节点
    d3.select(event.currentTarget).select('circle').classed('highlighted', true);

    // 高亮连接的边和节点
    links.forEach(link => {
        const sourceId = getNodeId(link.source);
        const targetId = getNodeId(link.target);
        if (sourceId === d.id || targetId === d.id) {
            d3.selectAll('.link')
                .filter(l => getNodeId(l.source) === sourceId && getNodeId(l.target) === targetId && l.id === link.id)
                .classed('highlighted-link', true);

            // 高亮连接的节点
            if (sourceId !== d.id) {
                d3.selectAll('.node')
                    .filter(n => n.id === sourceId)
                    .select('circle')
                    .classed('highlighted', true);
            }
            if (targetId !== d.id) {
                d3.selectAll('.node')
                    .filter(n => n.id === targetId)
                    .select('circle')
                    .classed('highlighted', true);
            }
        }
    });
}

// 应用筛选
function applyFilters() {
    updateCurrentFilters();
    loadGraphData();
}

function clearGraph() {
    if (g) {
        g.selectAll('*').remove();
    }
    nodes = [];
    links = [];
    hideNodeInfo();
    hideEdgeInfo();
    setTimeout(syncPanelHeights, 0);
}

// 重置筛选
function resetFilters() {
    document.querySelectorAll('#year-filters input[type="checkbox"], #domain-filters input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    const companySelect = document.getElementById('company-select');
    if (companySelect) companySelect.value = '';

    document.getElementById('node-limit').value = 1000;
    document.getElementById('limit-value').textContent = 1000;

    currentFilters = {
        years: [],
        companies: [],
        esg_domains: [],
        limit: 1000
    };
    updateFilterCheckboxes();
    if (typeof window.refreshFilterToggleStates === "function") {
        window.refreshFilterToggleStates();
    }
    clearGraph();
    hideLoading();
}

// 适应屏幕
function fitGraph() {
    const bounds = g.node().getBBox();
    const fullWidth = document.getElementById('graph-container').clientWidth;
    const fullHeight = getCanvasHeight();

    const midX = bounds.x + bounds.width / 2;
    const midY = bounds.y + bounds.height / 2;

    const scale = 0.9 / Math.max(bounds.width / fullWidth, bounds.height / fullHeight);
    const translate = [fullWidth / 2 - scale * midX, fullHeight / 2 - scale * midY];

    svg.transition()
        .duration(750)
        .call(zoom.transform, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale));
}

// 缩放控制
function zoomIn() {
    svg.transition().call(zoom.scaleBy, 1.2);
}

function zoomOut() {
    svg.transition().call(zoom.scaleBy, 0.8);
}

function resetZoom() {
    svg.transition().call(zoom.transform, d3.zoomIdentity);
}

// 重置视图
function resetView() {
    resetFilters();
    applyFilters();
    fitGraph();
}

// 调整图表大小
function resizeGraph() {
    const container = document.getElementById('graph-container');
    const svgElement = container.querySelector('svg');
    syncPanelHeights();

    if (svgElement) {
        svgElement.setAttribute('width', container.clientWidth);
        svgElement.setAttribute('height', getCanvasHeight());
        if (simulation) {
            simulation.force('center', d3.forceCenter(container.clientWidth / 2, getCanvasHeight() / 2));
            simulation.alpha(0.25).restart();
        }
        fitGraph();
    }
}

// 显示统计信息
function showStats() {
    const modal = new bootstrap.Modal(document.getElementById('statsModal'));
    const content = document.getElementById('stats-content');

    content.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    `;

    modal.show();

    fetch(buildApiUrl('/stats', new URLSearchParams()))
        .then(response => response.json())
        .then(data => {
            content.innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <h6>Nodes by ESG Domain</h6>
                        <div class="stats-chart" id="domain-chart"></div>
                    </div>
                    <div class="col-md-6">
                        <h6>Nodes by Type</h6>
                        <div class="stats-chart" id="type-chart"></div>
                    </div>
                </div>
                <div class="row mt-3">
                    <div class="col-12">
                        <h6>Top Relationship Types</h6>
                        <div class="table-responsive">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>Relationship Type</th>
                                        <th>Count</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${Object.entries(data.edges_by_type || {}).slice(0, 10).map(([type, count]) =>
                                        `<tr><td>${type}</td><td>${count}</td></tr>`
                                    ).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `;

            // 创建简单的图表
            createSimpleChart('domain-chart', data.nodes_by_domain || {});
            createSimpleChart('type-chart', data.nodes_by_type || {});
        })
        .catch(error => {
            console.error('Error loading stats:', error);
            content.innerHTML = '<div class="alert alert-danger">Error loading statistics</div>';
        });
}

function createSimpleChart(containerId, data) {
    const container = document.getElementById(containerId);
    const colors = ['#28a745', '#007bff', '#6f42c1', '#dc3545', '#ffc107'];

    let html = '<div class="d-flex flex-column">';
    let i = 0;
    for (const [key, value] of Object.entries(data)) {
        html += `
            <div class="d-flex align-items-center mb-2">
                <div class="legend-color" style="background-color: ${colors[i % colors.length]}"></div>
                <span class="flex-grow-1">${key}</span>
                <span class="badge bg-secondary">${value}</span>
            </div>
        `;
        i++;
    }
    html += '</div>';

    container.innerHTML = html;
}

// 显示加载状态
function showLoading() {
    document.getElementById('loading').style.display = 'block';
}

function hideLoading() {
    document.getElementById('loading').style.display = 'none';
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initGraph();
    setTimeout(syncPanelHeights, 0);

    // 绑定滑块事件
    document.getElementById('node-limit').addEventListener('input', function() {
        document.getElementById('limit-value').textContent = this.value;
    });

    // 监听窗口大小变化
    window.addEventListener('resize', function() {
        // 防抖处理，避免频繁触发
        clearTimeout(window.resizeTimeout);
        window.resizeTimeout = setTimeout(() => {
            resizeGraph();
        }, 250);
    });
});

function getCanvasHeight() {
    const canvas = document.getElementById('graph-container');
    return Math.max(420, Math.floor(canvas ? canvas.getBoundingClientRect().height : 0));
}

function syncPanelHeights() {
    const filterCard = document.querySelector('.filters-card');
    const graphCard = document.querySelector('.graph-card');
    const graphBody = graphCard ? graphCard.querySelector('.graph-card__body') : null;
    const canvas = document.getElementById('graph-container');
    if (!filterCard || !graphCard || !graphBody || !canvas) return;

    const header = graphCard.querySelector('.graph-card__header');
    const headerHeight = header ? header.getBoundingClientRect().height : 0;
    const bodyStyles = window.getComputedStyle(graphBody);
    const bodyPadding = parseFloat(bodyStyles.paddingTop || '0') + parseFloat(bodyStyles.paddingBottom || '0');
    const nav = document.querySelector('.top-nav');
    const navHeight = nav ? nav.getBoundingClientRect().height : 72;
    const targetHeight = Math.max(420, Math.floor(window.innerHeight - navHeight - 8));

    const canvasHeight = Math.max(420, targetHeight - headerHeight - bodyPadding);
    canvas.style.height = `${canvasHeight}px`;

    const svgElement = canvas.querySelector('svg');
    if (svgElement) {
        svgElement.setAttribute('width', canvas.clientWidth);
        svgElement.setAttribute('height', canvasHeight);
    }

    graphCard.style.minHeight = `${targetHeight}px`;
    graphCard.style.height = `${targetHeight}px`;
    filterCard.style.minHeight = `${targetHeight}px`;
    filterCard.style.height = `${targetHeight}px`;
}
