const COLORS = {
    environmental: '#3fb950',
    social: '#58a6ff',
    governance: '#bc8cff',
    ai: '#f0883e',
};

const DOMAIN_LABELS = {
    environmental: 'Environmental',
    social: 'Social',
    governance: 'Governance',
    ai: 'AI',
};

const SENTIMENT_COLORS = {
    positive: '#3fb950',
    neutral: '#8b949e',
    negative: '#f85149',
};

const NODE_SIZES = {
    COMPANY: 12, TECHNOLOGY: 10, AI_SYSTEM: 10, ESG_INITIATIVE: 8,
    ESG_METRIC: 7, OUTCOME: 7, ESG_FACTOR: 6, RISK_FACTOR: 6,
    STAKEHOLDER: 6, REGULATORY_FRAMEWORK: 6, DEFAULT: 5,
};

let svg, simulation, gLinks, gNodes, gLabels, tooltip, defs;
let currentData = { nodes: [], edges: [] };
let currentView = 'summary'; // 'summary' or 'detail'

// Drill-down state
let _drillLevel = 0;       // 0=summary, 1=subcluster/xd-bipartite, 2=community-detail
let _currentCluster = null;
let _currentSubclusterData = null;
let _currentCrossDomainData = null;  // set when bipartite view is active
let _clusterDetailCache = {};

function _dropIsolated(nodes, edges) {
    const connected = new Set();
    edges.forEach(e => { connected.add(e.source); connected.add(e.target); });
    return nodes.filter(n => connected.has(n.id));
}

function escapeHtml(str) {
    if (str == null) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function humanize(str) {
    if (!str) return '';
    return str.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    svg = d3.select('#graph');
    tooltip = d3.select('#tooltip');

    const width = svg.node().parentElement.clientWidth;
    const height = svg.node().parentElement.clientHeight;
    svg.attr('viewBox', [0, 0, width, height]);

    defs = svg.append('defs');

    // Arrow markers
    defs.append('marker')
        .attr('id', 'arrow-forward')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20).attr('refY', 0)
        .attr('markerWidth', 6).attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path').attr('d', 'M0,-4L10,0L0,4').attr('fill', '#484f58');

    defs.append('marker')
        .attr('id', 'arrow-backward')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 10).attr('refY', 0)
        .attr('markerWidth', 6).attr('markerHeight', 6)
        .attr('orient', 'auto-start-reverse')
        .append('path').attr('d', 'M0,-4L10,0L0,4').attr('fill', '#484f58');

    defs.append('marker')
        .attr('id', 'arrow-bidir-end')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20).attr('refY', 0)
        .attr('markerWidth', 5).attr('markerHeight', 5)
        .attr('orient', 'auto')
        .append('path').attr('d', 'M0,-4L10,0L0,4').attr('fill', '#484f58');

    defs.append('marker')
        .attr('id', 'arrow-bidir-start')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', -10).attr('refY', 0)
        .attr('markerWidth', 5).attr('markerHeight', 5)
        .attr('orient', 'auto')
        .append('path').attr('d', 'M10,-4L0,0L10,4').attr('fill', '#484f58');

    const zoom = d3.zoom()
        .scaleExtent([0.1, 5])
        .on('zoom', (event) => container.attr('transform', event.transform));
    svg.call(zoom);

    const container = svg.append('g');
    gLinks = container.append('g').attr('class', 'links');
    gNodes = container.append('g').attr('class', 'nodes');
    gLabels = container.append('g').attr('class', 'labels');

    simulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(120))
        .force('charge', d3.forceManyBody().strength(-200))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => (d.size || getNodeSize(d)) + 8));

    // View toggle
    document.getElementById('view-summary').addEventListener('click', () => switchView('summary'));
    document.getElementById('view-detail').addEventListener('click', () => switchView('detail'));

    const slider = document.getElementById('node-limit');
    const limitLabel = document.getElementById('limit-value');
    slider.addEventListener('input', () => { limitLabel.textContent = slider.value; });
    slider.addEventListener('change', () => { if (currentView === 'detail') loadGraph(); });

    document.getElementById('apply-btn').addEventListener('click', () => loadCurrentView());
    document.getElementById('show-all-btn').addEventListener('click', () => {
        slider.value = slider.max;
        limitLabel.textContent = slider.max;
        loadGraph();
    });

    document.getElementById('back-to-summary').addEventListener('click', _navBack);

    initFilters();
});

function switchView(view) {
    currentView = view;
    document.getElementById('view-summary').classList.toggle('active', view === 'summary');
    document.getElementById('view-detail').classList.toggle('active', view === 'detail');

    // Show/hide detail-only controls
    document.querySelectorAll('.detail-only').forEach(el => {
        el.style.display = view === 'detail' ? '' : 'none';
    });
    document.getElementById('drill-panel').style.display = view === 'summary' ? '' : 'none';
    const timeline = document.getElementById('year-timeline');
    if (timeline) timeline.style.display = view === 'summary' ? 'flex' : 'none';

    loadCurrentView();
}

function loadCurrentView() {
    if (currentView === 'summary') {
        loadClusterGraph();
    } else {
        loadGraph();
    }
}

// ---------- Filters ----------

let allCompanies = [], allYears = [], allDomains = [];

async function initFilters() {
    try {
        const resp = await fetch('/api/filters');
        const data = await resp.json();
        allCompanies = data.companies || [];
        allYears = data.years || [];
        allDomains = data.domains || [];

        const companyDiv = document.getElementById('company-filters');
        companyDiv.innerHTML = allCompanies.map(c => `
            <label class="filter-item">
                <input type="checkbox" class="company-cb" value="${escapeHtml(c)}" checked>
                ${escapeHtml(c)}
            </label>`).join('');

        const yearDiv = document.getElementById('year-filters');
        yearDiv.innerHTML = allYears.map(y => `
            <label class="filter-item">
                <input type="checkbox" class="year-cb" value="${y}">
                ${y}
            </label>`).join('');

        const domainDiv = document.getElementById('domain-filters');
        domainDiv.innerHTML = allDomains.map(d => {
            const color = COLORS[d] || '#8b949e';
            const label = DOMAIN_LABELS[d] || humanize(d);
            return `<label class="filter-item">
                <input type="checkbox" class="domain-cb" value="${escapeHtml(d)}">
                <span class="color-dot" style="background:${color}"></span>
                ${escapeHtml(label)}
            </label>`;
        }).join('');

        // Build year timeline track for summary view
        const timeline = document.getElementById('year-timeline');
        if (timeline && allYears.length > 0) {
            const sortedYears = [...allYears].sort();
            const trackWidth = Math.max(sortedYears.length * 100, 200);
            let html = `<div style="display:flex; align-items:center; position:relative; width:${trackWidth}px; height:40px;">`;
            // Track line
            html += `<div style="position:absolute; top:50%; left:20px; right:20px; height:3px; background:linear-gradient(90deg, #CBD5E1, #3B82F6); border-radius:2px; transform:translateY(-50%);"></div>`;
            // Year dots
            sortedYears.forEach((y, i) => {
                const pct = sortedYears.length === 1 ? 50 : (i / (sortedYears.length - 1)) * 80 + 10;
                html += `<div class="year-dot" data-year="${y}" style="position:absolute; left:${pct}%; transform:translateX(-50%); cursor:pointer; text-align:center; z-index:2;">
                    <div class="dot-circle" style="width:16px; height:16px; border-radius:50%; background:white; border:3px solid #CBD5E1; margin:0 auto; transition:all 0.2s;"></div>
                    <div class="dot-label" style="font-size:12px; font-weight:600; color:#64748B; margin-top:2px; transition:all 0.2s;">${y}</div>
                </div>`;
            });
            html += '</div>';
            timeline.innerHTML = html;

            timeline.querySelectorAll('.year-dot').forEach(dot => {
                dot.addEventListener('click', () => {
                    const wasActive = dot.classList.contains('active');
                    // Reset all dots
                    timeline.querySelectorAll('.year-dot').forEach(d => {
                        d.classList.remove('active');
                        d.querySelector('.dot-circle').style.background = 'white';
                        d.querySelector('.dot-circle').style.borderColor = '#CBD5E1';
                        d.querySelector('.dot-circle').style.width = '16px';
                        d.querySelector('.dot-circle').style.height = '16px';
                        d.querySelector('.dot-label').style.color = '#64748B';
                        d.querySelector('.dot-label').style.fontSize = '12px';
                    });
                    // Sync sidebar
                    document.querySelectorAll('.year-cb').forEach(cb => cb.checked = false);
                    if (!wasActive) {
                        dot.classList.add('active');
                        dot.querySelector('.dot-circle').style.background = '#3B82F6';
                        dot.querySelector('.dot-circle').style.borderColor = '#3B82F6';
                        dot.querySelector('.dot-circle').style.width = '20px';
                        dot.querySelector('.dot-circle').style.height = '20px';
                        dot.querySelector('.dot-label').style.color = '#1E293B';
                        dot.querySelector('.dot-label').style.fontSize = '14px';
                        const yearCb = document.querySelector(`.year-cb[value="${dot.dataset.year}"]`);
                        if (yearCb) yearCb.checked = true;
                    }
                    loadClusterGraph();
                });
                // Hover effect
                dot.addEventListener('mouseenter', () => {
                    if (!dot.classList.contains('active')) {
                        dot.querySelector('.dot-circle').style.borderColor = '#93C5FD';
                        dot.querySelector('.dot-circle').style.background = '#EFF6FF';
                    }
                });
                dot.addEventListener('mouseleave', () => {
                    if (!dot.classList.contains('active')) {
                        dot.querySelector('.dot-circle').style.borderColor = '#CBD5E1';
                        dot.querySelector('.dot-circle').style.background = 'white';
                    }
                });
            });

            // Auto-select latest year
            const latestDot = timeline.querySelector(`.year-dot[data-year="${sortedYears[sortedYears.length - 1]}"]`);
            if (latestDot) latestDot.click();
        }

        document.querySelectorAll('.company-cb').forEach(cb => {
            cb.addEventListener('change', onCompanyChange);
        });
        document.querySelectorAll('.year-cb, .domain-cb').forEach(cb => {
            cb.addEventListener('change', () => loadCurrentView());
        });

        fetch('/api/total_count').then(r => r.json()).then(tc => {
            const slider = document.getElementById('node-limit');
            slider.max = tc.total_nodes || 2000;
            slider.step = 1;
            slider.value = slider.max;
            document.getElementById('limit-value').textContent = slider.max;
        }).catch(() => {});

        await onCompanyChange();
    } catch (e) {
        console.error('Failed to init filters:', e);
    }
}

async function onCompanyChange() {
    const selectedCompanies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const params = new URLSearchParams();
    selectedCompanies.forEach(c => params.append('companies', c));
    const resp = await fetch(`/api/filters?${params}`);
    const data = await resp.json();
    const activeYears = new Set((data.active_years || []).map(String));
    const activeDomains = new Set(data.active_domains || []);

    document.querySelectorAll('.year-cb').forEach(cb => { cb.checked = activeYears.has(cb.value); });
    document.querySelectorAll('.domain-cb').forEach(cb => { cb.checked = activeDomains.has(cb.value); });

    loadCurrentView();
}

// ---------- Summary (Cluster) View ----------

async function loadClusterGraph() {
    const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);
    const domains = [...document.querySelectorAll('.domain-cb:checked')].map(cb => cb.value);

    const params = new URLSearchParams();
    companies.forEach(c => params.append('companies', c));
    years.forEach(y => params.append('years', y));
    domains.forEach(d => params.append('domains', d));

    try {
        const resp = await fetch(`/api/cluster-graph?${params}`);
        const data = await resp.json();
        renderClusterGraph(data);
        updateClusterStats(data);
    } catch (e) {
        console.error('Failed to load cluster graph:', e);
    }
}

function renderClusterGraph(data) {
    gLinks.selectAll('*').remove();
    gNodes.selectAll('*').remove();
    gLabels.selectAll('*').remove();

    if (!data.nodes || !data.nodes.length) {
        simulation.nodes([]);
        simulation.force('link').links([]);
        return;
    }

    const width = svg.node().parentElement.clientWidth;
    const height = svg.node().parentElement.clientHeight;

    // Position clusters in a triangle layout: E/S/G as vertices, AI at center
    const cx = width / 2;
    const cy = height / 2;
    const r = Math.min(width, height) * 0.32;
    const positions = {
        'Environmental': { x: cx, y: cy - r },                           // top vertex
        'Social':        { x: cx - r * Math.cos(Math.PI / 6), y: cy + r * Math.sin(Math.PI / 6) + r * 0.2 },  // bottom-left
        'Governance':    { x: cx + r * Math.cos(Math.PI / 6), y: cy + r * Math.sin(Math.PI / 6) + r * 0.2 },  // bottom-right
        'AI':            { x: cx, y: cy + r * 0.05 },                    // center
    };

    data.nodes.forEach(n => {
        const pos = positions[n.id] || { x: width / 2, y: height / 2 };
        n.x = pos.x;
        n.y = pos.y;
        n.fx = pos.x;
        n.fy = pos.y;
    });

    // Draw edges with weight-based width
    const link = gLinks.selectAll('line')
        .data(data.edges)
        .enter().append('line')
        .attr('class', 'link cluster-link')
        .attr('stroke-width', d => d.width)
        .attr('stroke-opacity', 0.6)
        .attr('x1', d => {
            const src = data.nodes.find(n => n.id === d.source);
            return src ? src.x : 0;
        })
        .attr('y1', d => {
            const src = data.nodes.find(n => n.id === d.source);
            return src ? src.y : 0;
        })
        .attr('x2', d => {
            const tgt = data.nodes.find(n => n.id === d.target);
            return tgt ? tgt.x : 0;
        })
        .attr('y2', d => {
            const tgt = data.nodes.find(n => n.id === d.target);
            return tgt ? tgt.y : 0;
        })
        .on('mouseover', (event, d) => {
            const src = typeof d.source === 'object' ? d.source.id : d.source;
            const tgt = typeof d.target === 'object' ? d.target.id : d.target;
            const html = `<strong>${escapeHtml(src)} ↔ ${escapeHtml(tgt)}</strong><br>
                ${d.weight} triples<br>
                ${d.top_relations.map(r => `${escapeHtml(r.type)}: ${r.count}`).join('<br>')}
                <br><em style="color:#58a6ff">Click to explore</em>`;
            tooltip.style('display', 'block')
                .style('left', (event.pageX + 15) + 'px')
                .style('top', (event.pageY - 10) + 'px')
                .html(html);
        })
        .on('mouseout', () => tooltip.style('display', 'none'))
        .on('click', (event, d) => {
            const src = typeof d.source === 'object' ? d.source.id : d.source;
            const tgt = typeof d.target === 'object' ? d.target.id : d.target;
            drillDownCrossCluster(src, tgt);
        })
        .style('cursor', 'pointer');

    // Edge weight labels
    gLabels.selectAll('text.edge-label')
        .data(data.edges.filter(e => e.source !== e.target))
        .enter().append('text')
        .attr('class', 'edge-label')
        .attr('text-anchor', 'middle')
        .attr('fill', '#8b949e')
        .attr('font-size', '11px')
        .attr('x', d => {
            const src = data.nodes.find(n => n.id === d.source);
            const tgt = data.nodes.find(n => n.id === d.target);
            return src && tgt ? (src.x + tgt.x) / 2 : 0;
        })
        .attr('y', d => {
            const src = data.nodes.find(n => n.id === d.source);
            const tgt = data.nodes.find(n => n.id === d.target);
            return src && tgt ? (src.y + tgt.y) / 2 - 8 : 0;
        })
        .text(d => `${d.weight}`);

    // Draw cluster nodes
    const node = gNodes.selectAll('g')
        .data(data.nodes)
        .enter().append('g')
        .attr('class', 'node cluster-node')
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .style('cursor', 'pointer')
        .on('click', (event, d) => drillDownCluster(d.id));

    node.append('circle')
        .attr('r', d => d.size)
        .attr('fill', d => d.color)
        .attr('fill-opacity', 0.15)
        .attr('stroke', d => d.color)
        .attr('stroke-width', 3);

    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', -5)
        .attr('fill', d => d.color)
        .attr('font-size', '16px')
        .attr('font-weight', 'bold')
        .text(d => d.label);

    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', 15)
        .attr('fill', '#8b949e')
        .attr('font-size', '12px')
        .text(d => `${d.concept_count} concepts · ${d.triple_count} triples`);

    // Hover effect
    node.on('mouseover', function(event, d) {
        d3.select(this).select('circle').attr('fill-opacity', 0.3);
    }).on('mouseout', function(event, d) {
        d3.select(this).select('circle').attr('fill-opacity', 0.15);
    });

    // Stop simulation for static layout
    simulation.nodes([]).force('link').links([]);
}

function _navBack() {
    if (_drillLevel === 2) {
        _drillLevel = 1;
        if (_currentCrossDomainData) {
            // Entity detail → cross-domain bipartite view
            const d = _currentCrossDomainData;
            document.getElementById('drill-info').textContent =
                `${humanize(d.domain1)} ↔ ${humanize(d.domain2)}: ${d.edges.length} community connections · ${d.cross_triple_count} cross-domain triples`;
            _setBackBtn(true, '← Back to Summary');
            renderCrossDomainCommunities(d);
            updateCrossDomainStats(d);
        } else {
            // Entity detail → sub-cluster view
            document.getElementById('drill-info').textContent =
                `${humanize(_currentCluster)}: ${_currentSubclusterData.nodes.length} communities · ${_currentSubclusterData.total_triples} triples`;
            _setBackBtn(true, `← Back to Summary`);
            renderSubClusterGraph(_currentSubclusterData, _currentCluster);
            updateSubClusterStats(_currentSubclusterData);
        }
    } else {
        // Level 1 → summary
        _drillLevel = 0;
        _currentCluster = null;
        _currentCrossDomainData = null;
        _setBackBtn(false, '← Back');
        document.getElementById('drill-info').textContent = 'Click a cluster node to explore its concepts';
        loadClusterGraph();
    }
}

function _setBackBtn(visible, label) {
    const btn = document.getElementById('back-to-summary');
    const floatBtn = document.getElementById('back-to-summary-float');
    btn.style.display = visible ? 'inline-block' : 'none';
    btn.textContent = label;
    if (floatBtn) {
        floatBtn.style.display = visible ? 'block' : 'none';
        floatBtn.textContent = label;
    }
}

async function drillDownCluster(clusterId) {
    const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);

    const params = new URLSearchParams();
    params.set('cluster', clusterId.toLowerCase());
    companies.forEach(c => params.append('companies', c));
    years.forEach(y => params.append('years', y));

    _currentCluster = clusterId.toLowerCase();
    _currentCrossDomainData = null;
    _drillLevel = 1;
    document.getElementById('drill-info').textContent = `${clusterId}: grouping by ontology concepts...`;
    _setBackBtn(true, '← Back to Summary');

    try {
        const resp = await fetch(`/api/cluster-subgraph?${params}`);
        const data = await resp.json();

        if (data.error) {
            // Fallback: go straight to detail if Louvain unavailable
            document.getElementById('drill-info').textContent = `Showing: ${clusterId} cluster concepts`;
            params.set('limit', '200');
            const fallback = await fetch(`/api/cluster-detail?${params}`);
            currentData = await fallback.json();
            renderGraph(currentData);
            updateStats();
            return;
        }

        _currentSubclusterData = data;
        document.getElementById('drill-info').textContent =
            `${clusterId}: ${data.nodes.length} ontology groups · ${data.total_triples} triples — click a group to explore`;
        renderSubClusterGraph(data, clusterId);
        updateSubClusterStats(data);

        // Prefetch cluster detail in background for fast community drill-down
        const detailParams = new URLSearchParams(params);
        detailParams.set('limit', '500');
        fetch(`/api/cluster-detail?${detailParams}`)
            .then(r => r.json())
            .then(detail => { _clusterDetailCache[_currentCluster] = detail; })
            .catch(() => {});
    } catch (e) {
        console.error('Failed to load sub-communities:', e);
    }
}

function renderSubClusterGraph(data, clusterName) {
    gLinks.selectAll('*').remove();
    gNodes.selectAll('*').remove();
    gLabels.selectAll('*').remove();

    if (!data.nodes || !data.nodes.length) {
        simulation.nodes([]).force('link').links([]);
        return;
    }

    const width = svg.node().parentElement.clientWidth;
    const height = svg.node().parentElement.clientHeight;
    const cx = width / 2;
    const cy = height / 2;
    const n = data.nodes.length;
    // Radius grows with node count so they never overlap regardless of how many there are
    const minR = Math.min(width, height) * (n <= 3 ? 0.22 : 0.32);
    const perNodeArc = 90; // px between node centers around the circle
    const r = Math.max(minR, (n * perNodeArc) / (2 * Math.PI));

    // Circular layout — deterministic, no simulation needed
    data.nodes.forEach((node, i) => {
        const angle = (2 * Math.PI * i / n) - Math.PI / 2;
        node.x = n === 1 ? cx : cx + r * Math.cos(angle);
        node.y = n === 1 ? cy : cy + r * Math.sin(angle);
        node.fx = node.x;
        node.fy = node.y;
    });

    // Edges
    gLinks.selectAll('line')
        .data(data.edges)
        .enter().append('line')
        .attr('class', 'link cluster-link')
        .attr('stroke-width', d => d.width || 1)
        .attr('stroke-opacity', 0.4)
        .attr('x1', d => { const s = data.nodes.find(nd => nd.id === d.source); return s ? s.x : 0; })
        .attr('y1', d => { const s = data.nodes.find(nd => nd.id === d.source); return s ? s.y : 0; })
        .attr('x2', d => { const t = data.nodes.find(nd => nd.id === d.target); return t ? t.x : 0; })
        .attr('y2', d => { const t = data.nodes.find(nd => nd.id === d.target); return t ? t.y : 0; });

    // Edge weight labels
    gLabels.selectAll('text.edge-label')
        .data(data.edges)
        .enter().append('text')
        .attr('class', 'edge-label')
        .attr('text-anchor', 'middle')
        .attr('fill', '#8b949e')
        .attr('font-size', '10px')
        .attr('x', d => {
            const s = data.nodes.find(nd => nd.id === d.source);
            const t = data.nodes.find(nd => nd.id === d.target);
            return s && t ? (s.x + t.x) / 2 : 0;
        })
        .attr('y', d => {
            const s = data.nodes.find(nd => nd.id === d.source);
            const t = data.nodes.find(nd => nd.id === d.target);
            return s && t ? (s.y + t.y) / 2 - 6 : 0;
        })
        .text(d => d.weight);

    // Community nodes
    const node = gNodes.selectAll('g')
        .data(data.nodes)
        .enter().append('g')
        .attr('class', 'node cluster-node')
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .style('cursor', d => d.id === 'comm_other' ? 'default' : 'pointer')
        .on('click', (event, d) => drillDownSubcommunity(d))
        .on('mouseover', function(event, d) {
            d3.select(this).select('circle').attr('fill-opacity', 0.35);
            const hint = d.id === 'comm_other'
                ? '<em style="color:#8b949e">Highly-specific concepts (not drillable)</em>'
                : '<em style="color:#58a6ff">Click to explore</em>';
            tooltip.style('display', 'block')
                .style('left', (event.pageX + 15) + 'px')
                .style('top', (event.pageY - 10) + 'px')
                .html(`<strong>${escapeHtml(d.label)}</strong><br>
                    ${d.concept_count} concepts · ${d.triple_count} triples<br>
                    ${hint}`);
        })
        .on('mouseout', function() {
            d3.select(this).select('circle').attr('fill-opacity', 0.15);
            tooltip.style('display', 'none');
        });

    node.append('circle')
        .attr('r', d => d.size)
        .attr('fill', d => d.color)
        .attr('fill-opacity', 0.15)
        .attr('stroke', d => d.color)
        .attr('stroke-width', 2.5)
        .attr('stroke-dasharray', d => d.id === 'comm_other' ? '6,4' : null);

    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', -7)
        .attr('fill', d => d.color)
        .attr('font-size', '13px')
        .attr('font-weight', 'bold')
        .text(d => d.label);

    node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', 10)
        .attr('fill', '#8b949e')
        .attr('font-size', '11px')
        .text(d => `${d.concept_count} concepts`);

    simulation.nodes([]).force('link').links([]);
}

async function drillDownSubcommunity(commNode) {
    // "Other" bucket is too large and too noisy to visualise meaningfully
    if (commNode.id === 'comm_other') {
        document.getElementById('drill-info').textContent =
            `"Other" contains ${commNode.concept_count} highly-specific concepts that don't cluster together — try a named community.`;
        return;
    }
    _drillLevel = 2;
    document.getElementById('drill-info').textContent =
        `${humanize(_currentCluster)} › ${commNode.label} (${commNode.concept_count} concepts)`;
    _setBackBtn(true, `← Back to ${humanize(_currentCluster)} Communities`);

    const memberSet = new Set(commNode.members);

    // Use prefetched cache or fetch on demand
    let clusterDetail = _clusterDetailCache[_currentCluster];
    if (!clusterDetail) {
        const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
        const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);
        const params = new URLSearchParams();
        params.set('cluster', _currentCluster);
        params.set('limit', '500');
        companies.forEach(c => params.append('companies', c));
        years.forEach(y => params.append('years', y));
        const resp = await fetch(`/api/cluster-detail?${params}`);
        clusterDetail = await resp.json();
        _clusterDetailCache[_currentCluster] = clusterDetail;
    }

    // Show all edges where at least one endpoint is a community member,
    // and include the other-side nodes too so cross-community links are visible.
    const allNodesById = Object.fromEntries(clusterDetail.nodes.map(n => [n.id, n]));
    const memberNodeIds = new Set(clusterDetail.nodes.filter(n => memberSet.has(n.label)).map(n => n.id));
    const filteredEdges = clusterDetail.edges.filter(
        e => memberNodeIds.has(e.source) || memberNodeIds.has(e.target)
    );
    const neededIds = new Set();
    filteredEdges.forEach(e => { neededIds.add(e.source); neededIds.add(e.target); });
    const filteredNodes = clusterDetail.nodes.filter(n => neededIds.has(n.id));

    currentData = { nodes: filteredNodes, edges: filteredEdges };
    renderGraph(currentData);
    updateStats();
}

function updateSubClusterStats(data) {
    const statsDiv = document.getElementById('stats');
    let html = `<div style="color:#8b949e;font-size:10px;text-transform:uppercase;margin-bottom:6px;letter-spacing:.05em">Grouping: Ontology Concepts</div>`;
    html += `<div class="stat-row"><span>Groups</span><span>${data.nodes.length}</span></div>`;
    html += `<div class="stat-row"><span>Total Triples</span><span>${data.total_triples}</span></div>`;
    html += '<div style="margin-top:8px;border-top:1px solid #30363d;padding-top:8px">';
    data.nodes.forEach(n => {
        html += `<div class="stat-row">
            <span><span class="color-dot" style="background:${n.color};display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:50%"></span>${escapeHtml(n.label)}</span>
            <span>${n.concept_count}</span>
        </div>`;
    });
    html += '</div>';
    statsDiv.innerHTML = html;
    document.getElementById('gw-panel').innerHTML = '';
}

async function drillDownCrossCluster(cluster1, cluster2) {
    const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);
    const params = new URLSearchParams();
    companies.forEach(c => params.append('companies', c));
    years.forEach(y => params.append('years', y));
    _setBackBtn(true, '← Back to Summary');

    if (cluster1.toLowerCase() === cluster2.toLowerCase()) {
        // Self-loop: show raw entity graph for this domain
        params.set('cluster1', cluster1.toLowerCase());
        params.set('cluster2', cluster2.toLowerCase());
        params.set('limit', '300');
        document.getElementById('drill-info').textContent = `Showing: ${humanize(cluster1)} internal triples`;
        try {
            const resp = await fetch(`/api/cross-cluster-detail?${params}`);
            currentData = await resp.json();
            renderGraph(currentData);
            updateStats();
        } catch (e) { console.error('cross-cluster-detail failed:', e); }
        return;
    }

    // Cross-domain: show community bipartite view
    params.set('domain1', cluster1.toLowerCase());
    params.set('domain2', cluster2.toLowerCase());
    document.getElementById('drill-info').textContent =
        `${humanize(cluster1)} ↔ ${humanize(cluster2)}: loading community connections...`;
    _drillLevel = 1;

    try {
        const resp = await fetch(`/api/cross-domain-communities?${params}`);
        const data = await resp.json();
        if (data.error || (!data.nodes_d1.length && !data.nodes_d2.length)) {
            document.getElementById('drill-info').textContent =
                `${humanize(cluster1)} ↔ ${humanize(cluster2)}: no named community connections found (${data.cross_triple_count || 0} cross-domain triples exist but entities lack ontology labels)`;
            return;
        }
        document.getElementById('drill-info').textContent =
            `${humanize(cluster1)} ↔ ${humanize(cluster2)}: ${data.edges.length} community connections · ${data.cross_triple_count} cross-domain triples`;
        renderCrossDomainCommunities(data);
        updateCrossDomainStats(data);
    } catch (e) { console.error('cross-domain-communities failed:', e); }
}

function renderCrossDomainCommunities(data) {
    _currentCrossDomainData = data;
    gLinks.selectAll('*').remove();
    gNodes.selectAll('*').remove();
    gLabels.selectAll('*').remove();

    const width = svg.node().parentElement.clientWidth;
    const height = svg.node().parentElement.clientHeight;

    const COLORS = { environmental: '#3fb950', social: '#58a6ff', governance: '#bc8cff', ai: '#f0883e' };
    const d1 = data.domain1;
    const d2 = data.domain2;
    const xLeft = width * 0.25;
    const xRight = width * 0.75;

    const sortedD1 = [...data.nodes_d1].sort((a, b) => b.concept_count - a.concept_count);
    const sortedD2 = [...data.nodes_d2].sort((a, b) => b.concept_count - a.concept_count);
    const maxRows = Math.max(sortedD1.length, sortedD2.length, 1);
    const rowH = Math.min(70, (height - 100) / maxRows);
    const startY = (height - rowH * (maxRows - 1)) / 2;

    const nodes = [];
    sortedD1.forEach((n, i) => nodes.push({ ...n, x: xLeft,  y: startY + i * rowH, side: 'left'  }));
    sortedD2.forEach((n, i) => nodes.push({ ...n, x: xRight, y: startY + i * rowH, side: 'right' }));
    const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));

    // Domain header labels
    [[d1, xLeft], [d2, xRight]].forEach(([domain, x]) => {
        gLabels.append('text')
            .attr('x', x).attr('y', 36)
            .attr('text-anchor', 'middle')
            .attr('fill', COLORS[domain] || '#8b949e')
            .attr('font-size', '15px').attr('font-weight', 'bold')
            .text(domain.charAt(0).toUpperCase() + domain.slice(1));
    });

    // Edges — clickable to show cross-domain triples between two communities
    const maxW = Math.max(...data.edges.map(e => e.weight), 1);
    gLinks.selectAll('line')
        .data(data.edges)
        .enter().append('line')
        .attr('stroke', '#8b949e')
        .attr('stroke-width', d => Math.max(2, (d.weight / maxW) * 8))
        .attr('stroke-opacity', 0.35)
        .attr('x1', d => nodeById[d.source]?.x || 0)
        .attr('y1', d => nodeById[d.source]?.y || 0)
        .attr('x2', d => nodeById[d.target]?.x || 0)
        .attr('y2', d => nodeById[d.target]?.y || 0)
        .style('cursor', 'pointer')
        .on('mouseover', function(event, d) {
            d3.select(this).attr('stroke-opacity', 0.8).attr('stroke', '#e3b341');
            const src = nodeById[d.source];
            const tgt = nodeById[d.target];
            tooltip.style('display', 'block')
                .style('left', (event.pageX + 15) + 'px')
                .style('top', (event.pageY - 10) + 'px')
                .html(`<strong>${escapeHtml(src?.label)} ↔ ${escapeHtml(tgt?.label)}</strong><br>${d.weight} cross-domain triples<br><em>Click to see entity connections</em>`);
        })
        .on('mouseout', function() {
            d3.select(this).attr('stroke-opacity', 0.35).attr('stroke', '#8b949e');
            tooltip.style('display', 'none');
        })
        .on('click', (event, d) => {
            const src = nodeById[d.source];
            const tgt = nodeById[d.target];
            if (src && tgt) drillIntoXDEdge(src, tgt);
        });

    gLabels.selectAll('text.edge-label')
        .data(data.edges)
        .enter().append('text')
        .attr('class', 'edge-label')
        .attr('text-anchor', 'middle')
        .attr('fill', '#8b949e')
        .attr('font-size', '10px')
        .attr('x', d => ((nodeById[d.source]?.x || 0) + (nodeById[d.target]?.x || 0)) / 2)
        .attr('y', d => ((nodeById[d.source]?.y || 0) + (nodeById[d.target]?.y || 0)) / 2 - 4)
        .style('pointer-events', 'none')
        .text(d => d.weight);

    // Nodes — clickable to show entity graph for that community
    const nodeR = 18;
    const node = gNodes.selectAll('g')
        .data(nodes)
        .enter().append('g')
        .attr('class', 'node cluster-node')
        .attr('transform', d => `translate(${d.x},${d.y})`)
        .style('cursor', 'pointer')
        .on('mouseover', function(event, d) {
            d3.select(this).select('circle').attr('fill-opacity', 0.35);
            const sdc = d.same_domain_count ? ` · ${d.same_domain_count} in domain` : '';
            tooltip.style('display', 'block')
                .style('left', (event.pageX + 15) + 'px')
                .style('top', (event.pageY - 10) + 'px')
                .html(`<strong>${escapeHtml(d.label)}</strong><br>${escapeHtml(d.domain)}<br>${d.concept_count} cross-domain triples${sdc}<br><em>Click to explore entities</em>`);
        })
        .on('mouseout', function() {
            d3.select(this).select('circle').attr('fill-opacity', 0.15);
            tooltip.style('display', 'none');
        })
        .on('click', (event, d) => drillIntoXDCommunity(d));

    node.append('circle')
        .attr('r', nodeR)
        .attr('fill', d => COLORS[d.domain] || '#8b949e')
        .attr('fill-opacity', 0.15)
        .attr('stroke', d => COLORS[d.domain] || '#8b949e')
        .attr('stroke-width', 2);

    // Labels outside the circle, flipped per side
    node.append('text')
        .attr('text-anchor', d => d.side === 'left' ? 'end' : 'start')
        .attr('x', d => d.side === 'left' ? -nodeR - 6 : nodeR + 6)
        .attr('dy', '-0.2em')
        .attr('fill', d => COLORS[d.domain] || '#ccc')
        .attr('font-size', '12px').attr('font-weight', 'bold')
        .text(d => d.label);

    node.append('text')
        .attr('text-anchor', d => d.side === 'left' ? 'end' : 'start')
        .attr('x', d => d.side === 'left' ? -nodeR - 6 : nodeR + 6)
        .attr('dy', '1.1em')
        .attr('fill', '#8b949e')
        .attr('font-size', '10px')
        .text(d => `${d.concept_count} triples`);

    simulation.nodes([]).force('link').links([]);
}

async function drillIntoXDCommunity(nodeData) {
    _drillLevel = 2;
    const domain = nodeData.domain;
    const backLabel = `← Back to ${humanize(_currentCrossDomainData?.domain1)} ↔ ${humanize(_currentCrossDomainData?.domain2)}`;
    document.getElementById('drill-info').textContent =
        `${humanize(domain)} › ${nodeData.label} (${nodeData.same_domain_count || nodeData.concept_count} entities)`;
    _setBackBtn(true, backLabel);

    // members = same-domain entities, cross_members = cross-domain entities — use both
    const memberSet = new Set([...(nodeData.members || []), ...(nodeData.cross_members || [])]);
    if (!memberSet.size) {
        document.getElementById('drill-info').textContent += ' — no member data available';
        return;
    }

    // Fetch cross-domain triples too so cross_members entities are found
    const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);

    let clusterDetail = _clusterDetailCache[domain];
    if (!clusterDetail) {
        const params = new URLSearchParams();
        params.set('cluster', domain);
        params.set('limit', '500');
        companies.forEach(c => params.append('companies', c));
        years.forEach(y => params.append('years', y));
        const resp = await fetch(`/api/cluster-detail?${params}`);
        clusterDetail = await resp.json();
        _clusterDetailCache[domain] = clusterDetail;
    }

    // cross_members may only appear in cross-domain triples — fetch those too
    const xdomain = _currentCrossDomainData?.domain1 === domain
        ? _currentCrossDomainData?.domain2 : _currentCrossDomainData?.domain1;
    let xdDetail = xdomain ? _clusterDetailCache[`xd_${domain}_${xdomain}`] : null;
    if (xdomain && !xdDetail) {
        const params = new URLSearchParams();
        params.set('cluster1', domain);
        params.set('cluster2', xdomain);
        params.set('limit', '500');
        companies.forEach(c => params.append('companies', c));
        years.forEach(y => params.append('years', y));
        const resp = await fetch(`/api/cross-cluster-detail?${params}`);
        xdDetail = await resp.json();
        _clusterDetailCache[`xd_${domain}_${xdomain}`] = xdDetail;
    }

    // Merge both graphs
    // Merge both graphs, dedup by node id only (different years = different nodes intentionally)
    const allNodesMap = Object.fromEntries(
        [...(clusterDetail.nodes || []), ...(xdDetail?.nodes || [])].map(n => [n.id, n])
    );
    const allNodes = Object.values(allNodesMap);
    const allEdges = [...(clusterDetail.edges || []), ...(xdDetail?.edges || [])];

    const memberNodeIds = new Set(allNodes.filter(n => memberSet.has(n.label)).map(n => n.id));
    const filteredEdges = allEdges.filter(
        e => memberNodeIds.has(e.source) || memberNodeIds.has(e.target)
    );
    const neededIds = new Set();
    filteredEdges.forEach(e => { neededIds.add(e.source); neededIds.add(e.target); });
    const filteredNodes = allNodes.filter(n => neededIds.has(n.id));

    currentData = { nodes: filteredNodes, edges: filteredEdges };
    renderGraph(currentData);
    updateStats();
}

async function drillIntoXDEdge(srcNode, tgtNode) {
    _drillLevel = 2;
    const backLabel = `← Back to ${humanize(_currentCrossDomainData?.domain1)} ↔ ${humanize(_currentCrossDomainData?.domain2)}`;
    document.getElementById('drill-info').textContent =
        `${srcNode.label} ↔ ${tgtNode.label}: loading cross-domain entities...`;
    _setBackBtn(true, backLabel);

    const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);
    const params = new URLSearchParams();
    params.set('cluster1', srcNode.domain);
    params.set('cluster2', tgtNode.domain);
    params.set('limit', '500');
    companies.forEach(c => params.append('companies', c));
    years.forEach(y => params.append('years', y));

    try {
        const resp = await fetch(`/api/cross-cluster-detail?${params}`);
        const allData = await resp.json();

        // cross_members = entities from cross-domain triples in this community
        // (members = same-domain only, so can't use that here)
        const srcMembers = new Set(srcNode.cross_members?.length ? srcNode.cross_members : srcNode.members || []);
        const tgtMembers = new Set(tgtNode.cross_members?.length ? tgtNode.cross_members : tgtNode.members || []);
        const allowedNodes = new Set([...srcMembers, ...tgtMembers]);

        const srcNodeIds = new Set(allData.nodes.filter(n => srcMembers.has(n.label)).map(n => n.id));
        const tgtNodeIds = new Set(allData.nodes.filter(n => tgtMembers.has(n.label)).map(n => n.id));
        // Only edges that actually cross between the two communities
        const filteredEdges = allData.edges.filter(
            e => (srcNodeIds.has(e.source) && tgtNodeIds.has(e.target)) ||
                 (tgtNodeIds.has(e.source) && srcNodeIds.has(e.target))
        );
        const neededIds = new Set();
        filteredEdges.forEach(e => { neededIds.add(e.source); neededIds.add(e.target); });
        const filteredNodes = allData.nodes.filter(n => neededIds.has(n.id));

        document.getElementById('drill-info').textContent =
            `${srcNode.label} ↔ ${tgtNode.label}: ${filteredEdges.length} cross-domain triples`;

        currentData = { nodes: filteredNodes, edges: filteredEdges };
        renderGraph(currentData);
        updateStats();
    } catch (e) {
        console.error('drillIntoXDEdge failed:', e);
    }
}

function updateCrossDomainStats(data) {
    const COLORS = { environmental: '#3fb950', social: '#58a6ff', governance: '#bc8cff', ai: '#f0883e' };
    const statsDiv = document.getElementById('stats');
    let html = `<div style="color:#8b949e;font-size:10px;text-transform:uppercase;margin-bottom:6px">Cross-Domain Communities</div>`;
    html += `<div class="stat-row"><span>Cross-domain triples</span><span>${data.cross_triple_count}</span></div>`;
    html += `<div class="stat-row"><span>Community connections</span><span>${data.edges.length}</span></div>`;

    [[data.domain1, data.nodes_d1], [data.domain2, data.nodes_d2]].forEach(([domain, dnodes]) => {
        if (!dnodes.length) return;
        const col = COLORS[domain] || '#ccc';
        html += `<div style="margin-top:8px;border-top:1px solid #30363d;padding-top:6px">`;
        html += `<div style="color:${col};font-size:11px;font-weight:bold;margin-bottom:4px">${domain.charAt(0).toUpperCase() + domain.slice(1)}</div>`;
        dnodes.forEach(n => {
            html += `<div class="stat-row"><span style="color:${col}">${escapeHtml(n.label)}</span><span>${n.concept_count}</span></div>`;
        });
        html += `</div>`;
    });

    statsDiv.innerHTML = html;
    document.getElementById('gw-panel').innerHTML = '';
}

function updateClusterStats(data) {
    const statsDiv = document.getElementById('stats');
    let html = `<div class="stat-row"><span>Total Triples</span><span>${data.total_triples}</span></div>`;

    data.nodes.forEach(n => {
        html += `<div class="stat-row">
            <span><span class="color-dot" style="background:${n.color};display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:50%"></span>${n.label}</span>
            <span>${n.concept_count} concepts</span>
        </div>`;
    });

    const crossEdges = data.edges.filter(e => e.source !== e.target);
    if (crossEdges.length) {
        html += '<div style="margin-top:8px;border-top:1px solid #30363d;padding-top:8px">';
        html += '<div style="color:#8b949e;font-size:11px;text-transform:uppercase;margin-bottom:4px">Cross-Domain Links</div>';
        crossEdges.sort((a, b) => b.weight - a.weight);
        crossEdges.forEach(e => {
            html += `<div class="stat-row"><span>${e.source} → ${e.target}</span><span>${e.weight}</span></div>`;
        });
        html += '</div>';
    }

    statsDiv.innerHTML = html;
    document.getElementById('gw-panel').innerHTML = '';
}

// ---------- Detail View ----------

async function loadGreenwashing() {
    try {
        const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
        const panel = document.getElementById('gw-panel');
        if (!panel || !companies.length) { if (panel) panel.innerHTML = ''; return; }

        let html = '<div style="border-top:1px solid #30363d;padding-top:8px;margin-top:4px">';
        html += '<div style="color:#8b949e;font-size:11px;text-transform:uppercase;margin-bottom:6px">Greenwashing Risk</div>';

        for (const company of companies) {
            const resp = await fetch(`/api/greenwashing?company=${encodeURIComponent(company)}`);
            const gw = await resp.json();
            const riskColor = gw.risk_level === 'HIGH' ? '#f85149'
                : gw.risk_level === 'MEDIUM' ? '#d29922' : '#3fb950';

            html += `<div style="margin-bottom:8px">
                <div class="stat-row"><strong>${escapeHtml(company)}</strong><span>${gw.total_triples} triples</span></div>
                <div class="stat-row"><span>GW Index</span>
                    <span style="color:${riskColor};font-weight:bold">${gw.greenwashing_index} (${gw.risk_level})</span></div>
                <div class="stat-row"><span>Credibility</span><span>${gw.credibility_avg || '-'}/5</span></div>
                <div class="stat-row"><span>Quantitative</span><span>${gw.quantitative_ratio}%</span></div>
            </div>`;
        }
        html += '</div>';
        panel.innerHTML = html;
    } catch (e) {
        console.error('Failed to load greenwashing:', e);
    }
}

async function loadGraph() {
    const domains = [...document.querySelectorAll('.domain-cb:checked')].map(cb => cb.value);
    const companies = [...document.querySelectorAll('.company-cb:checked')].map(cb => cb.value);
    const years = [...document.querySelectorAll('.year-cb:checked')].map(cb => cb.value);
    const limit = document.getElementById('node-limit').value;

    if (!domains.length || !companies.length || !years.length) {
        currentData = { nodes: [], edges: [] };
        renderGraph(currentData);
        updateStats();
        return;
    }

    const params = new URLSearchParams();
    domains.forEach(d => params.append('domains', d));
    companies.forEach(c => params.append('companies', c));
    years.forEach(y => params.append('years', y));
    params.set('limit', limit);

    try {
        const resp = await fetch(`/api/graph?${params}`);
        currentData = await resp.json();
        renderGraph(currentData);
        updateStats();
        loadGreenwashing();
    } catch (e) {
        console.error('Failed to load graph:', e);
    }
}

function getNodeSize(d) { return NODE_SIZES[d.type] || NODE_SIZES.DEFAULT; }
function getNodeColor(d) { return COLORS[d.esg_domain] || '#8b949e'; }

function getEdgeMarkers(d) {
    const dir = d.direction || 'e1_to_e2';
    if (dir === 'e1_to_e2') return { start: null, end: 'url(#arrow-forward)' };
    if (dir === 'e2_to_e1') return { start: 'url(#arrow-backward)', end: null };
    return { start: 'url(#arrow-bidir-start)', end: 'url(#arrow-bidir-end)' };
}

function getEdgeStyle(d) {
    const cred = d.credibility_score || 0;
    if (cred >= 3) return { width: 2.5, dash: null, opacity: 0.7 };
    if (cred >= 1) return { width: 1.5, dash: null, opacity: 0.4 };
    return { width: 1, dash: '4,3', opacity: 0.3 };
}

function renderGraph(data) {
    // Drop nodes with no edges before rendering
    const nodes = _dropIsolated(data.nodes, data.edges);
    data = { ...data, nodes };

    gLinks.selectAll('*').remove();
    gNodes.selectAll('*').remove();
    gLabels.selectAll('*').remove();

    if (!data.nodes.length) {
        simulation.nodes([]);
        simulation.force('link').links([]);
        return;
    }

    const link = gLinks.selectAll('line')
        .data(data.edges)
        .enter().append('line')
        .attr('class', 'link')
        .each(function(d) {
            const markers = getEdgeMarkers(d);
            const style = getEdgeStyle(d);
            const el = d3.select(this);
            el.attr('stroke-width', style.width).attr('stroke-opacity', style.opacity);
            if (style.dash) el.attr('stroke-dasharray', style.dash);
            if (markers.end) el.attr('marker-end', markers.end);
            if (markers.start) el.attr('marker-start', markers.start);
        })
        .on('mouseover', (event, d) => showEdgeTooltip(event, d))
        .on('mouseout', () => tooltip.style('display', 'none'));

    const node = gNodes.selectAll('g')
        .data(data.nodes)
        .enter().append('g')
        .attr('class', 'node')
        .call(d3.drag()
            .on('start', dragStart)
            .on('drag', dragging)
            .on('end', dragEnd));

    node.append('circle')
        .attr('r', d => getNodeSize(d))
        .attr('fill', d => getNodeColor(d))
        .on('mouseover', (event, d) => {
            d3.select(event.target).attr('r', getNodeSize(d) * 1.5);
            showNodeTooltip(event, d);
        })
        .on('mouseout', (event, d) => {
            d3.select(event.target).attr('r', getNodeSize(d));
            tooltip.style('display', 'none');
        });

    node.append('text')
        .attr('dx', d => getNodeSize(d) + 4)
        .attr('dy', 3)
        .text(d => d.label ? humanize(d.label).substring(0, 30) : '');

    simulation.nodes(data.nodes).on('tick', () => {
        link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    simulation.force('link').links(data.edges);
    simulation.alpha(1).restart();
}

function showNodeTooltip(event, d) {
    tooltip.style('display', 'block')
        .style('left', (event.pageX + 15) + 'px')
        .style('top', (event.pageY - 10) + 'px')
        .html(`<strong>${escapeHtml(humanize(d.label))}</strong><br>
               Type: ${escapeHtml(d.type)}<br>
               Domain: <span class="domain-${d.esg_domain}">${escapeHtml(DOMAIN_LABELS[d.esg_domain] || d.esg_domain)}</span><br>
               ${escapeHtml(d.company)} ${d.year}`);
}

function showEdgeTooltip(event, d) {
    const credBar = '\u2605'.repeat(Math.round(d.credibility_score || 0)) +
                    '\u2606'.repeat(5 - Math.round(d.credibility_score || 0));
    const sentColor = SENTIMENT_COLORS[d.sentiment] || '#8b949e';
    const sourceNode = typeof d.source === 'object' ? d.source : currentData.nodes.find(n => n.id === d.source);
    const targetNode = typeof d.target === 'object' ? d.target : currentData.nodes.find(n => n.id === d.target);
    const sourceColor = sourceNode ? (COLORS[sourceNode.esg_domain] || '#8b949e') : '#8b949e';
    const targetColor = targetNode ? (COLORS[targetNode.esg_domain] || '#8b949e') : '#8b949e';

    let html = `<h3 style="color:#58a6ff;margin:0 0 10px 0;font-size:15px">${escapeHtml(d.type)}</h3>
        <div style="margin-bottom:6px">
            <div style="color:#8b949e;font-size:11px;text-transform:uppercase">Source</div>
            <div style="color:${sourceColor};font-size:13px">${escapeHtml(sourceNode ? humanize(sourceNode.label) : '')}
                <span style="color:#8b949e;font-size:11px"> (${escapeHtml(sourceNode?.type || '')})</span></div>
        </div>
        <div style="margin-bottom:6px">
            <div style="color:#8b949e;font-size:11px;text-transform:uppercase">Action</div>
            <div style="font-size:13px">${escapeHtml(d.action)}</div>
        </div>
        <div style="margin-bottom:6px">
            <div style="color:#8b949e;font-size:11px;text-transform:uppercase">Target</div>
            <div style="color:${targetColor};font-size:13px">${escapeHtml(targetNode ? humanize(targetNode.label) : '')}
                <span style="color:#8b949e;font-size:11px"> (${escapeHtml(targetNode?.type || '')})</span></div>
        </div>
        <div style="margin-bottom:6px">
            <div style="color:#8b949e;font-size:11px;text-transform:uppercase">Credibility</div>
            <div style="font-size:13px">${credBar} (${d.credibility_score || 0}/5)</div>
        </div>
        <div style="margin-bottom:6px">
            <div style="color:#8b949e;font-size:11px;text-transform:uppercase">Sentiment</div>
            <div style="font-size:13px;color:${sentColor}">${d.sentiment || 'neutral'}</div>
        </div>`;

    if (d.evidence) {
        html += `<div>
            <div style="color:#8b949e;font-size:11px;text-transform:uppercase">Evidence</div>
            <div style="background:#0d1117;padding:8px;border-radius:4px;border-left:3px solid #58a6ff;font-style:italic;font-size:12px;line-height:1.5;margin-top:4px">
                ${escapeHtml(d.evidence)}
            </div>
        </div>`;
    }

    tooltip.style('display', 'block')
        .style('left', (event.pageX + 20) + 'px')
        .style('top', (event.pageY - 20) + 'px')
        .html(html);
}

function updateStats() {
    const statsDiv = document.getElementById('stats');
    const domainCounts = {};
    currentData.nodes.forEach(n => {
        domainCounts[n.esg_domain] = (domainCounts[n.esg_domain] || 0) + 1;
    });

    let html = `<div class="stat-row"><span>Nodes</span><span>${currentData.nodes.length}</span></div>
                <div class="stat-row"><span>Edges</span><span>${currentData.edges.length}</span></div>
                <div style="margin-top:8px"></div>`;
    Object.entries(domainCounts).sort((a, b) => b[1] - a[1]).forEach(([domain, cnt]) => {
        const color = COLORS[domain] || '#8b949e';
        const label = DOMAIN_LABELS[domain] || domain;
        html += `<div class="stat-row">
            <span><span class="color-dot" style="background:${color};display:inline-block;width:8px;height:8px;margin-right:4px;border-radius:50%"></span>${label}</span>
            <span>${cnt}</span>
        </div>`;
    });
    statsDiv.innerHTML = html;
}

function dragStart(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x; d.fy = d.y;
}
function dragging(event, d) { d.fx = event.x; d.fy = event.y; }
function dragEnd(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null; d.fy = null;
}
