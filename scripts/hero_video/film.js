/* The hero film's timeline. Builds a replica of the contract desk for one language, then
   `window.__seek(t)` sets every moving property from the time, so any frame can be rendered
   on its own and the result is identical every run. Content is synthetic. */
const q = new URLSearchParams(location.search);
const W = +q.get('w') || 1920, H = +q.get('h') || 1080;
const PORTRAIT = q.get('mode') === 'portrait';
const LANG = q.get('lang') === 'en' ? 'en' : 'zh';
const DURATION = 26;

/* ----------------------------------------------------------------- copy */
const STR = {
  zh: {
    title: 'CausalGraph — 合同审查', library: '合同库', file: '采购合同（2026 版）.docx',
    steps: ['脱敏', '设置', '审查', '处理', '导出'], policies: '公司规范', avatar: '法', lang: ['中文', 'EN'],
    clauses: '条款', sections: '7 段',
    outline: ['标的与规格', '合同价款', '交付', '付款', '验收', '违约责任', '争议解决'],
    meta: [['类型', '采购合同'], ['我方', '采购方'], ['档位', '标准审查'], ['模型', 'GLM-5.2'], ['范围', '18 项']],
    scopeDone: '18/18 已审查',
    found: '识别到 6 处敏感信息', redacted: n => `已脱敏 ${n} 处`, legend: ['高风险', '中风险', '提示', '待核实'],
    sheetTitle: '采购合同', sheetNo: '合同编号：CG-2026-0917',
    partyA: '甲方（采购方）：', partyB: '乙方（供应方）：', contact: '联系人：', tel: '　电话：',
    entityA: '杭州云禾科技有限公司', entityB: '苏州明澜精密制造有限公司', person: '张晓敏', phone: '138 2345 6789', amount: '1,280,000 元', account: '6222 0210 0088 5312',
    tokens: ['主体1', '主体2', '姓名1', '电话1', '金额1', '账号1'],
    cl: [
      ['第一条　标的与规格', '乙方向甲方供应精密结构件（型号 ML-240）共计 12,000 件，技术参数、材质及包装要求详见附件一《产品规格书》。'],
      ['第二条　合同价款', '本合同总价为人民币 {amount}（含税），单价及明细见附件二《价格清单》。'],
      ['第三条　交付', '乙方应于本合同签订后 45 日内，将全部货物交付至甲方指定地点，运输费用由乙方承担。'],
      ['第四条　付款', '4.1　甲方应在{rl1}支付全部价款。4.2　付款至乙方指定账户：{account}。'],
      ['第五条　验收', '甲方应在收货后 7 日内完成验收；验收标准由乙方另行确定。'],
      ['第六条　违约责任', '6.1　任何一方违约，应向守约方支付合同总价 {rl2} 的违约金；6.2　因不可抗力不能履行的，根据影响部分或全部免除责任。'],
      ['第七条　争议解决', '因本合同引起的争议，双方应协商解决；协商不成的，提交乙方所在地有管辖权的人民法院诉讼解决。'],
    ],
    rl1: ['合同签订后 5 日内', '验收合格后 30 日内'], rl2: ['50%', '20%'],
    sign: '甲方（盖章）：　　　　　　　　　　乙方（盖章）：', date: '日期：2026 年　　月　　日', foot: '第 1 页 · 共 1 页',
    redactTitle: '脱敏核对', redactSub: '模型分析前，敏感信息先替换为占位符。你可以逐处对照原件核对。',
    confirmRedact: '确认脱敏', compare: '对照原件',
    setupTitle: '审查设置', contractType: '合同类型', contractTypeValue: '采购合同', ourParty: '我方身份', roles: ['采购方', '供应方'],
    depth: '审查档位', tiers: ['极速', '快速', '标准', '深度'], tierNote: '分组审查与法规检索同时进行，逐项复核后核对各项修改能否同时采用。',
    model: '审查模型', modelValue: 'GLM-5.2', consent: '同意将脱敏后的合同文本经 YData 网关提交所选模型分析', start: '开始审查',
    reviewing: '审查中', phase: n => `分项审查 · 已完成 ${n}/5 项`,
    agents: ['法律风险审查', '公司利益审查', '公司规范审查', '证据与覆盖复核', '全文协调与冲突检查'], done: '已完成',
    agentNotes: [
      ['第 1/3 项：主体、授权与合同效力', '第 2/3 项：违约、赔偿与免责', '第 3/3 项：争议解决与全文一致性'],
      ['第 1/3 项：交付、验收与付款', '第 2/3 项：预付款与交付保障', '第 3/3 项：验收、隐蔽缺陷与质保'],
      ['对照 2 条适用公司规范'],
      ['复核：付款与交付保障', '复核：违约金与法定依据'],
      ['合并重复意见 · 检查条款冲突'],
    ],
    feedTitle: '审查动态',
    feed: [
      ['00:05', '已提交审查', '标准审查 · GLM-5.2'],
      ['00:17', '公司利益审查', '第 4.1 条 付款早于验收，资金风险集中在我方'],
      ['00:31', '法律风险审查', '第 6.1 条 违约金约定过高 · 《民法典》第五百八十五条'],
      ['00:43', '公司规范审查', '第 5 条 验收标准单方确定，与《采购管理办法》不一致'],
      ['00:58', '证据与覆盖复核', '18/18 项要点已覆盖 · 2 条依据已核验'],
    ],
    notesCount: '条批注', prio: '2 项高风险建议优先处理', tabs: ['批注 3', '问答', '依据'],
    notes: [
      { level: 'hi', levelText: '高风险', kind: '公司利益', where: '第 4.1 条', title: '付款早于验收，资金风险集中在我方',
        impact: '全部价款在验收前支付，交付或质量问题的损失由我方先行承担。', reasonLabel: '风险说明', reason: '付款条件未与验收结果挂钩，货物不符时缺少制衡手段。',
        editLabel: '修改建议', before: '甲方应在', del: '合同签订后 5 日内', ins: '验收合格后 30 日内', after: '支付全部价款。' },
      { level: 'mid', levelText: '中风险', kind: '法律风险', where: '第 6.1 条', title: '违约金约定明显过高',
        impact: '合同总价 50% 远超可能的损失，法院可依请求予以减少。', reasonLabel: '法律依据', reason: '《中华人民共和国民法典》第五百八十五条：约定的违约金过分高于造成的损失的，可以请求予以适当减少。',
        editLabel: '修改建议', before: '应向守约方支付合同总价 ', del: '50%', ins: '20%', after: ' 的违约金。' },
      { level: 'hi', levelText: '高风险', kind: '法律风险', where: '第 5 条', title: '验收标准由乙方单方确定',
        impact: '我方将受制于未经双方确认的验收标准。', reasonLabel: '风险说明', reason: '验收标准应由双方书面确认，并与附件一规格书一致。',
        editLabel: '修改建议', before: '验收标准', del: '由乙方另行确定', ins: '以附件一《产品规格书》为准，并经双方书面确认', after: '。' },
    ],
    adopt: '采纳修改', keep: '保留原文', adopted: '已采纳 · 已写入修订', handled: '已处理', exportBtn: '导出',
    exportTitle: '导出', exportSub: '报告可随时导出；修订版需核验并确认后生成。',
    checks: [['采纳修改', '已采纳 2 项'], ['组合核验', '2 处修改与原文一致，可同时采用'], ['确认修订', '已核对全部修改及剩余风险']],
    docx: 'Word 修订版', docxSub: '保留原有格式 · 含修订痕迹', exportDocx: '导出修订版',
    fileName: '采购合同（2026 版）· 修订版.docx', fileMeta: '2 处修订痕迹 · 192 KB', ready: '已生成',
    disclaimer: '审查结果仅供参考，不构成法律意见。',
  },
  en: {
    title: 'CausalGraph — Contract review', library: 'Library', file: 'Purchase Agreement (2026).docx',
    steps: ['Redact', 'Set up', 'Review', 'Decide', 'Export'], policies: 'Policies', avatar: 'L', lang: ['中文', 'EN'],
    clauses: 'Clauses', sections: '7 sections',
    outline: ['Subject and specifications', 'Contract price', 'Delivery', 'Payment', 'Acceptance', 'Liability for breach', 'Dispute resolution'],
    meta: [['Type', 'Purchase agreement'], ['Our party', 'Buyer'], ['Depth', 'Standard'], ['Model', 'GLM-5.2'], ['Scope', '18 items']],
    scopeDone: '18/18 reviewed',
    found: '6 sensitive items found', redacted: n => `${n} redacted`, legend: ['High', 'Medium', 'Note', 'Unverified'],
    sheetTitle: 'PURCHASE AGREEMENT', sheetNo: 'Contract No. CG-2026-0917',
    partyA: 'Party A (Buyer): ', partyB: 'Party B (Supplier): ', contact: 'Contact: ', tel: '   Tel: ',
    entityA: 'Hangzhou Yunhe Technology Co., Ltd.', entityB: 'Suzhou Minglan Precision Manufacturing Co., Ltd.', person: 'Zhang Xiaomin', phone: '138 2345 6789', amount: 'RMB 1,280,000', account: '6222 0210 0088 5312',
    tokens: ['Entity 1', 'Entity 2', 'Name 1', 'Phone 1', 'Amount 1', 'Account 1'],
    cl: [
      ['Article 1  Subject and specifications.', 'Party B shall supply 12,000 precision structural parts (model ML-240) to Party A. Technical parameters, materials and packaging are set out in Schedule 1 (Product Specification).'],
      ['Article 2  Contract price.', 'The total contract price is {amount} (inclusive of tax); unit prices are set out in Schedule 2 (Price List).'],
      ['Article 3  Delivery.', 'Party B shall deliver all goods to the location designated by Party A within 45 days of signing. Freight is borne by Party B.'],
      ['Article 4  Payment.', '4.1  Party A shall pay the full price {rl1}. 4.2  Payment shall be made to Party B’s account {account}.'],
      ['Article 5  Acceptance.', 'Party A shall complete acceptance within 7 days of receipt; the acceptance criteria shall be determined separately by Party B.'],
      ['Article 6  Liability for breach.', '6.1  A party in breach shall pay the other party liquidated damages equal to {rl2} of the total contract price. 6.2  Where performance is prevented by force majeure, liability is excused in whole or in part according to its effect.'],
      ['Article 7  Dispute resolution.', 'Disputes shall first be settled by negotiation; failing that, by the competent people’s court at Party B’s domicile.'],
    ],
    rl1: ['within 5 days of signing', 'within 30 days of acceptance'], rl2: ['50%', '20%'],
    sign: 'Party A (seal):                              Party B (seal):', date: 'Date:          2026', foot: 'Page 1 of 1',
    redactTitle: 'Redaction check', redactSub: 'Sensitive details become placeholders before any model sees the contract. Compare each one with the original.',
    confirmRedact: 'Confirm redaction', compare: 'Compare original',
    setupTitle: 'Review settings', contractType: 'Contract type', contractTypeValue: 'Purchase agreement', ourParty: 'Our party', roles: ['Buyer', 'Supplier'],
    depth: 'Review depth', tiers: ['Ultra-fast', 'Fast', 'Standard', 'Deep'], tierNote: 'Reviews in groups while researching the law, verifies each finding, then checks that the edits can be adopted together.',
    model: 'Model', modelValue: 'GLM-5.2', consent: 'Send the redacted contract to the selected model through the YData gateway', start: 'Start review',
    reviewing: 'Reviewing', phase: n => `Group review · ${n}/5 done`,
    agents: ['Legal risk', 'Commercial interest', 'Company policy', 'Evidence and coverage', 'Whole-contract consistency'], done: 'Done',
    agentNotes: [
      ['Item 1/3: Parties, authority and validity', 'Item 2/3: Breach, damages and exclusions', 'Item 3/3: Disputes and internal consistency'],
      ['Item 1/3: Delivery, acceptance and payment', 'Item 2/3: Advance payment and delivery security', 'Item 3/3: Acceptance, latent defects and warranty'],
      ['Checking 2 applicable company policies'],
      ['Verifying: payment and delivery security', 'Verifying: damages and statutory basis'],
      ['Merging duplicates · checking clause conflicts'],
    ],
    feedTitle: 'Live review feed',
    feed: [
      ['00:05', 'Review submitted', 'Standard · GLM-5.2'],
      ['00:17', 'Commercial interest', 'Clause 4.1 Payment before acceptance; the cash risk sits with us'],
      ['00:31', 'Legal risk', 'Clause 6.1 Liquidated damages excessive · Civil Code, Art. 585'],
      ['00:43', 'Company policy', 'Clause 5 Acceptance criteria set unilaterally; conflicts with the Procurement Policy'],
      ['00:58', 'Evidence and coverage', '18/18 items covered · 2 sources verified'],
    ],
    notesCount: 'findings', prio: '2 high-risk items to handle first', tabs: ['Findings 3', 'Q&A', 'Basis'],
    notes: [
      { level: 'hi', levelText: 'High', kind: 'Commercial', where: 'Clause 4.1', title: 'Payment before acceptance leaves the cash risk with us',
        impact: 'The full price is paid before acceptance, so delivery or quality problems are financed by us first.', reasonLabel: 'Risk note', reason: 'Payment is not tied to acceptance, leaving no leverage if the goods do not conform.',
        editLabel: 'Suggested edit', before: 'Party A shall pay the full price ', del: 'within 5 days of signing', ins: 'within 30 days of acceptance', after: '.' },
      { level: 'mid', levelText: 'Medium', kind: 'Legal', where: 'Clause 6.1', title: 'Liquidated damages are clearly excessive',
        impact: '50% of the contract price far exceeds the likely loss; a court may reduce it on request.', reasonLabel: 'Legal basis', reason: 'Civil Code of the PRC, Art. 585: liquidated damages that are excessively higher than the loss caused may be reduced on request.',
        editLabel: 'Suggested edit', before: 'liquidated damages equal to ', del: '50%', ins: '20%', after: ' of the total contract price.' },
      { level: 'hi', levelText: 'High', kind: 'Legal', where: 'Clause 5', title: 'Acceptance criteria set by the supplier alone',
        impact: 'We would be bound by criteria we never agreed to.', reasonLabel: 'Risk note', reason: 'Acceptance criteria should be confirmed by both parties in writing and match Schedule 1.',
        editLabel: 'Suggested edit', before: 'the acceptance criteria shall be ', del: 'determined separately by Party B', ins: 'those in Schedule 1, confirmed by both parties in writing', after: '.' },
    ],
    adopt: 'Accept edit', keep: 'Keep original', adopted: 'Accepted · written into the revision', handled: 'Handled', exportBtn: 'Export',
    exportTitle: 'Export', exportSub: 'Reports can be exported at any time; the revised version is generated after verification and confirmation.',
    checks: [['Accepted edits', '2 accepted'], ['Combined verification', '2 edits match the original and can be adopted together'], ['Confirm revision', 'All edits and remaining risks checked']],
    docx: 'Tracked-changes Word', docxSub: 'Original formatting kept · tracked changes', exportDocx: 'Export revision',
    fileName: 'Purchase Agreement (2026) · Revised.docx', fileMeta: '2 tracked changes · 192 KB', ready: 'Ready',
    disclaimer: 'Results are for reference only and are not legal advice.',
  },
};
const S = STR[LANG];

/* ------------------------------------------------------------------ dom */
const MARK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(120 12 12)"/></svg>';
const DOC = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>';
const CURSOR = '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M5 3l14 11.5h-7.1l-3.4 7.2z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/></svg><span class="ring"></span>';
const sens = (i, text) => `<span class="sens" id="sens${i}"><span class="orig">${text}</span><span class="chip">${S.tokens[i]}</span></span>`;
const rl = (id, pair) => `<span class="rl" id="${id}"><del>${pair[0]}</del><ins>${pair[1]}</ins></span>`;
const clauseText = (text) => text
  .replace('{amount}', sens(4, S.amount)).replace('{account}', sens(5, S.account))
  .replace('{rl1}', rl('rl1', S.rl1)).replace('{rl2}', rl('rl2', S.rl2));
const MARK_FOR = { 3: ['mk1', 'hi', 1], 4: ['mk2', 'hi', 2], 5: ['mk3', 'mid', 3] };

const html = `
<div class="stage" id="stage">
  <div class="glow"></div>
  <div class="window" id="win">
    <div class="titlebar"><span class="tl"></span><span class="tl"></span><span class="tl"></span><span class="title">${S.title}</span></div>
    <div class="desk">
      <header class="topbar">
        <div class="brand"><span class="mark">${MARK}</span>CausalGraph<span class="rule"></span><span class="crumb">${S.library}</span><span class="sep">/</span><span class="crumb current">${S.file}</span></div>
        <ol class="steps" id="steps">${S.steps.map((s, i) => `<li><span class="num">${i + 1}</span>${s}</li>`).join('')}</ol>
        <div class="topbar-end"><span class="policy">${S.policies}<b>2</b></span><span class="lang"><span class="${LANG === 'zh' ? 'on' : ''}">${S.lang[0]}</span><span class="${LANG === 'en' ? 'on' : ''}">${S.lang[1]}</span></span><span class="avatar">${S.avatar}</span></div>
      </header>
      <div class="body">
        <aside class="outline">
          <div class="outline-head"><b>${S.clauses}</b><span>${S.sections}</span></div>
          <ol class="outline-list">${S.outline.map((name, i) => `<li id="ol${i + 1}"><span class="on">${i + 1}</span><span class="ot">${name}</span><span class="om" id="om${i + 1}"></span></li>`).join('')}</ol>
          <dl class="outline-meta" id="outline-meta">${S.meta.map(([k, v], i) => `<div><dt>${k}</dt><dd id="meta${i}">${v}</dd></div>`).join('')}</dl>
        </aside>
        <main class="paper">
          <div class="paper-strip"><span class="file">${DOC}<b>${S.file}</b><span>·</span><span id="strip-redact">${S.found}</span></span><span class="legend" id="legend"><span><i class="hi"></i>${S.legend[0]}</span><span><i class="mid"></i>${S.legend[1]}</span><span><i class="low"></i>${S.legend[2]}</span><span><i class="un"></i>${S.legend[3]}</span></span></div>
          <div class="sheets"><article class="sheet" id="sheet">
            <h1 class="sheet-title">${S.sheetTitle}</h1>
            <p class="sheet-no">${S.sheetNo}</p>
            <section class="parties" id="parties">
              <p>${S.partyA}${sens(0, S.entityA)}</p>
              <p>${S.partyB}${sens(1, S.entityB)}</p>
              <p>${S.contact}${sens(2, S.person)}${S.tel}${sens(3, S.phone)}</p>
            </section>
            ${S.cl.map(([head, text], i) => `<p class="cl" id="cl${i + 1}">${MARK_FOR[i] ? `<span class="marker ${MARK_FOR[i][1]} mk" id="${MARK_FOR[i][0]}">${MARK_FOR[i][2]}</span>` : ''}<b>${head}</b>${clauseText(text)}</p>`).join('')}
            <p class="sign">${S.sign}<br>${S.date}</p>
            <div class="foot">${S.foot}</div>
          </article></div>
        </main>
        <aside class="rail" id="rail">
          <section class="panel" id="p-redact">
            <h2>${S.redactTitle}</h2><p class="sub">${S.redactSub}</p>
            <ul class="tokens">${[S.entityA, S.entityB, S.person, S.phone, S.amount, S.account].map((what, i) => `<li><span class="chip">${S.tokens[i]}</span><span class="what">${what}</span><span class="tick" id="tk${i}"></span></li>`).join('')}</ul>
            <div class="rail-actions"><span class="btn primary" id="btn-redact">${S.confirmRedact}</span><span class="btn secondary">${S.compare}</span></div>
          </section>
          <section class="panel" id="p-setup">
            <h2>${S.setupTitle}</h2>
            <div class="field"><label>${S.contractType}</label><div class="select">${S.contractTypeValue}<i class="chev"></i></div></div>
            <div class="field"><label>${S.ourParty}</label><div class="radios"><span class="radio on">${S.roles[0]}</span><span class="radio">${S.roles[1]}</span></div></div>
            <div class="field"><label>${S.depth}</label><div class="seg">${S.tiers.map((t, i) => `<span class="${i === 2 ? 'on' : ''}">${t}</span>`).join('')}</div><p class="hint">${S.tierNote}</p></div>
            <div class="field"><label>${S.model}</label><div class="select">${S.modelValue}<i class="chev"></i></div></div>
            <label class="consent" id="consent"><span class="box"></span><span>${S.consent}</span></label>
            <div class="rail-actions"><span class="btn primary" id="btn-start">${S.start}</span></div>
          </section>
          <section class="panel" id="p-review">
            <div class="review-head"><h2>${S.reviewing}</h2><span class="elapsed" id="elapsed">0:00</span></div>
            <div class="phase"><span id="phase-label">${S.phase(0)}</span><div class="bar"><i id="phase-bar"></i></div></div>
            <ul class="agents">${S.agents.map((name, i) => `<li><div class="ag-head"><span>${name}</span><span class="ag-state" id="ags${i}"></span></div><div class="bar"><i id="agb${i}"></i></div><p class="note" id="agn${i}"></p></li>`).join('')}</ul>
            <div class="feed"><div class="feed-head"><i class="dot"></i>${S.feedTitle}</div><ol id="feed">${S.feed.map((line, i) => `<li id="fd${i}"><time>${line[0]}</time><span><b>${line[1]}</b> · ${line[2]}</span></li>`).join('')}</ol></div>
          </section>
          <section class="panel" id="p-notes">
            <div class="notes-head"><span class="big">3</span><span class="label">${S.notesCount}</span><span class="prio">${S.prio}</span></div>
            <div class="tabs">${S.tabs.map((t, i) => `<span class="${i === 0 ? 'on' : ''}">${t}</span>`).join('')}</div>
            <div class="notes-list">${S.notes.map((n, i) => `
              <article class="note" id="n${i + 1}">
                <div class="note-row"><span class="marker ${n.level}">${i + 1}</span><div><div class="note-meta"><b class="${n.level}">${n.levelText}</b><span>·</span><span>${n.kind}</span><span class="where">${n.where}</span></div><h3>${n.title}</h3><p>${n.impact}</p></div></div>
                <div class="note-body" id="nb${i + 1}"><div>
                  <dl><dt>${n.reasonLabel}</dt><dd>${n.reason}</dd></dl>
                  <dl><dt>${n.editLabel}</dt><dd class="redline-box">${n.before}<del>${n.del}</del><ins>${n.ins}</ins>${n.after}</dd></dl>
                  <div class="note-actions"><span class="btn primary" id="btn-adopt${i + 1}">${S.adopt}<kbd>A</kbd></span><span class="btn secondary">${S.keep}<kbd>R</kbd></span></div>
                  <div class="adopted"><span class="tick on"></span>${S.adopted}</div>
                </div></div>
              </article>`).join('')}</div>
            <footer class="rail-foot"><span>${S.handled} <b id="done-count">0/3</b></span><div class="bar"><i id="done-bar"></i></div><span class="btn primary" id="btn-export">${S.exportBtn}</span></footer>
          </section>
          <section class="panel" id="p-export">
            <h2>${S.exportTitle}</h2><p class="sub">${S.exportSub}</p>
            <ul class="checks">${S.checks.map(([k, v], i) => `<li><span class="tick" id="ck${i}"></span><div><b>${k}</b><span class="d">${v}</span></div></li>`).join('')}</ul>
            <div class="export-row"><div><b>${S.docx}</b><span class="d">${S.docxSub}</span></div><span class="btn primary" id="btn-docx">${S.exportDocx}</span></div>
            <div class="file-card" id="file-card"><span class="docx">W</span><div><b>${S.fileName}</b><span class="d">${S.fileMeta}</span></div><span class="ok" id="file-ok"><span class="tick on"></span>${S.ready}</span></div>
            <p class="disclaimer">${S.disclaimer}</p>
          </section>
        </aside>
      </div>
    </div>
  </div>
  <div class="cursor" id="cursor">${CURSOR}</div>
</div>`;

const frame = document.getElementById('frame');
frame.style.width = W + 'px'; frame.style.height = H + 'px';
frame.classList.add('lang-' + LANG);
frame.innerHTML = html;
const $ = (id) => document.getElementById(id);
const stage = $('stage');

/* ---------------------------------------------------------------- utils */
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, p) => a + (b - a) * p;
const easeInOut = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
const easeOut = (p) => 1 - Math.pow(1 - p, 3);
const seg = (t, start, dur, ease = easeInOut) => ease(clamp((t - start) / dur));
const show = (el, p, dy = 8) => { el.style.opacity = p; el.style.transform = `translateY(${(1 - p) * dy}px)`; };

/** Centre of an element in stage coordinates, from the untransformed layout. */
function centre(target) {
  if (Array.isArray(target)) {
    const [a, b, w = 0.5] = target;
    const ca = centre(a), cb = centre(b);
    return { x: lerp(ca.x, cb.x, w), y: lerp(ca.y, cb.y, w) };
  }
  let el = document.querySelector(target), x = el.offsetWidth / 2, y = el.offsetHeight / 2;
  while (el && el !== stage) { x += el.offsetLeft; y += el.offsetTop; el = el.offsetParent; }
  return { x, y };
}
function corner(target, dx, dy) {
  const c = centre(target);
  return { x: c.x + dx, y: c.y + dy };
}

/* --------------------------------------------------------------- camera */
const WIN = { l: 180, t: 52, r: 1740, b: 1027 };
const CAMERA = PORTRAIT ? [
  [0.0, 1.12, ['#sheet', '#rail', 0.42]], [1.3, 1.12, ['#sheet', '#rail', 0.42]],
  [2.6, 1.5, '#parties'], [4.5, 1.5, '#parties'],
  [5.6, 1.42, '#p-setup'], [7.3, 1.42, '#p-setup'],
  [8.6, 1.3, '#p-review'], [12.6, 1.3, '#p-review'],
  [13.8, 1.4, '#n1'], [15.1, 1.4, '#n1'], [15.7, 1.45, '#cl4'], [16.4, 1.45, '#cl4'],
  [17.0, 1.4, '#n2'], [17.9, 1.4, '#n2'], [18.4, 1.45, '#cl6'], [19.0, 1.45, '#cl6'],
  [20.2, 1.4, '#p-export'], [22.6, 1.4, '#p-export'],
  [24.2, 1.12, ['#sheet', '#rail', 0.42]], [26.0, 1.12, ['#sheet', '#rail', 0.42]],
] : [
  [0.0, 1.0, '#win'], [1.3, 1.0, '#win'],
  [2.6, 1.32, '#parties'], [4.5, 1.32, '#parties'],
  [5.6, 1.3, '#p-setup'], [7.3, 1.3, '#p-setup'],
  [8.6, 1.0, '#win'], [12.6, 1.04, '#win'],
  [13.8, 1.3, ['#cl4', '#n1']], [16.3, 1.3, ['#cl4', '#n1']],
  [17.0, 1.3, ['#cl6', '#n2']], [19.0, 1.3, ['#cl6', '#n2']],
  [20.2, 1.26, '#p-export'], [22.6, 1.26, '#p-export'],
  [24.2, 1.0, '#win'], [26.0, 1.0, '#win'],
];
function camera(t) {
  let i = 0;
  while (i < CAMERA.length - 2 && t >= CAMERA[i + 1][0]) i++;
  const [t0, s0, f0] = CAMERA[i], [t1, s1, f1] = CAMERA[i + 1];
  const p = easeInOut(clamp((t - t0) / Math.max(0.001, t1 - t0)));
  const a = centre(f0), b = centre(f1);
  const s = lerp(s0, s1, p);
  let fx = lerp(a.x, b.x, p), fy = lerp(a.y, b.y, p);
  // Never look past the window's edge: when the view is smaller than the window in a
  // direction, keep it inside; when it is larger, centre the window in it.
  const halfW = W / (2 * s), halfH = H / (2 * s);
  fx = WIN.r - WIN.l > 2 * halfW ? clamp(fx, WIN.l + halfW, WIN.r - halfW) : (WIN.l + WIN.r) / 2;
  fy = WIN.b - WIN.t > 2 * halfH ? clamp(fy, WIN.t + halfH, WIN.b - halfH) : (WIN.t + WIN.b) / 2;
  stage.style.transform = `translate(${(W / 2 - fx * s).toFixed(2)}px, ${(H / 2 - fy * s).toFixed(2)}px) scale(${s.toFixed(4)})`;
}

/* --------------------------------------------------------------- cursor */
const CURSOR_PATH = [
  [3.9, '#btn-redact', 160, 90], [4.45, '#btn-redact', 0, 0], [4.75, '#btn-redact', 0, 0],
  [5.6, '#consent', -150, 0], [5.95, '#consent', -150, 0],
  [6.3, '#btn-start', 0, 0], [6.75, '#btn-start', 0, 0],
  [7.7, '#sheet', 400, 60],
  [12.6, '#sheet', 400, 60], [14.4, '#btn-adopt1', 0, 0], [15.0, '#btn-adopt1', 0, 0],
  [16.5, '#btn-adopt1', 0, 0], [17.2, '#btn-adopt2', 0, 0], [17.6, '#btn-adopt2', 0, 0],
  [18.4, '#btn-export', 0, 0], [19.0, '#btn-export', 0, 0],
  [20.3, '#btn-docx', 40, 60], [21.1, '#btn-docx', 0, 0], [21.6, '#btn-docx', 0, 0],
  [23.0, '#btn-docx', 70, 120],
];
const CLICKS = [4.75, 5.95, 6.75, 15.0, 17.6, 19.0, 21.6];
function cursor(t) {
  const el = $('cursor');
  const visible = seg(t, 3.9, 0.4, easeOut) * (1 - seg(t, 23.6, 0.6, easeOut));
  let i = 0;
  while (i < CURSOR_PATH.length - 2 && t >= CURSOR_PATH[i + 1][0]) i++;
  const [t0, e0, dx0, dy0] = CURSOR_PATH[i], [t1, e1, dx1, dy1] = CURSOR_PATH[i + 1];
  const p = easeInOut(clamp((t - t0) / Math.max(0.001, t1 - t0)));
  const a = corner(e0, dx0, dy0), b = corner(e1, dx1, dy1);
  const x = lerp(a.x, b.x, p), y = lerp(a.y, b.y, p);
  // a little overshoot-free arc so the pointer never slides in a straight line
  const arc = Math.sin(p * Math.PI) * Math.min(24, Math.hypot(b.x - a.x, b.y - a.y) * 0.12);
  let press = 0, ring = 0;
  for (const c of CLICKS) {
    press = Math.max(press, seg(t, c - 0.06, 0.06, easeOut) * (1 - seg(t, c + 0.04, 0.12, easeOut)));
    ring = Math.max(ring, seg(t, c, 0.45, easeOut) * (t >= c ? 1 : 0));
  }
  el.style.opacity = visible;
  el.style.transform = `translate(${(x - 4).toFixed(1)}px, ${(y - arc - 3).toFixed(1)}px) scale(${1 - press * 0.14})`;
  const r = el.querySelector('.ring');
  r.style.opacity = ring > 0 && ring < 1 ? 1 - ring : 0;
  r.style.transform = `scale(${0.4 + ring * 0.9})`;
  for (const c of CLICKS) {
    const target = CURSOR_PATH.find(k => Math.abs(k[0] - c) < 0.01);
    if (!target) continue;
    const btn = document.querySelector(target[1]);
    if (btn && btn.classList.contains('btn')) btn.classList.toggle('is-pressed', t >= c - 0.04 && t < c + 0.14);
  }
}

/* ------------------------------------------------------------- timeline */
const T = {
  redact: 1.4, redactStep: 0.5, confirm: 4.75, setup: 5.0, consent: 5.95, start: 6.75, review: 7.2,
  notes: 12.8, adopt1: 15.0, swap: 16.5, adopt2: 17.6, exportClick: 19.0, exportPanel: 19.3, docx: 21.6,
};
const PANELS = ['p-redact', 'p-setup', 'p-review', 'p-notes', 'p-export'];
const PANEL_AT = [0, T.setup, T.review, T.notes, T.exportPanel];
const AGENTS = [
  { start: 7.4, end: 11.6, notes: [7.4, 9.0, 10.4] },
  { start: 7.4, end: 11.0, notes: [7.4, 8.8, 10.0] },
  { start: 7.4, end: 9.6, notes: [7.4] },
  { start: 9.0, end: 12.2, notes: [9.0, 10.6] },
  { start: 11.6, end: 12.6, notes: [11.6] },
];
const FEED_AT = [7.6, 8.6, 9.8, 10.8, 12.0];
const READ_AT = [7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5];

function seek(t) {
  t = clamp(t, 0, DURATION);
  camera(t);

  // the window settles in
  const intro = seg(t, 0, 1.0, easeOut);
  const win = $('win');
  win.style.opacity = intro;
  win.style.transform = `scale(${lerp(0.97, 1, intro)})`;
  document.querySelector('.glow').style.opacity = intro;

  // steps
  const step = t < T.confirm ? 0 : t < T.start ? 1 : t < T.notes ? 2 : t < T.exportPanel ? 3 : 4;
  $('steps').querySelectorAll('li').forEach((li, i) => {
    li.classList.toggle('is-current', i === step);
    li.classList.toggle('is-done', i < step);
  });

  // rail panels cross-fade
  PANELS.forEach((id, i) => {
    const at = PANEL_AT[i], next = PANEL_AT[i + 1];
    const enter = i === 0 ? 1 : seg(t, at + 0.08, 0.45, easeOut);
    const leave = next == null ? 0 : seg(t, next, 0.3, easeOut);
    const el = $(id);
    el.style.opacity = enter * (1 - leave);
    el.style.transform = `translateY(${(1 - enter) * 10 - leave * 8}px)`;
    el.style.pointerEvents = 'none';
  });

  // redaction
  let redacted = 0;
  for (let i = 0; i < 6; i++) {
    const start = T.redact + i * T.redactStep;
    const sweep = seg(t, start, 0.32, easeInOut);
    const swap = t >= start + 0.3;
    const pop = seg(t, start + 0.3, 0.25, easeOut);
    const el = $('sens' + i), orig = el.querySelector('.orig'), chip = el.querySelector('.chip');
    orig.style.display = swap ? 'none' : 'inline';
    chip.style.display = swap ? 'inline-block' : 'none';
    chip.style.transform = `scale(${lerp(0.9, 1, pop)})`;
    chip.style.opacity = pop;
    // a highlight sweeps over the original just before it becomes a placeholder
    orig.style.background = sweep > 0 ? `linear-gradient(rgba(201,138,27,.28), rgba(201,138,27,.28)) no-repeat 0 0 / ${(sweep * 100).toFixed(1)}% 100%` : '';
    $('tk' + i).classList.toggle('on', t >= start + 0.42);
    if (swap) redacted++;
  }
  $('strip-redact').textContent = redacted ? S.redacted(redacted) : S.found;
  $('legend').style.opacity = seg(t, T.notes, 0.5, easeOut);

  // setup
  $('consent').classList.toggle('on', t >= T.consent);
  $('outline-meta').style.opacity = lerp(0.0, 1, seg(t, T.start, 0.5, easeOut));
  $('meta4').textContent = t >= T.notes ? S.scopeDone : S.meta[4][1];

  // review
  const elapsed = clamp((t - T.review) * 12, 0, 999);
  $('elapsed').textContent = `${Math.floor(elapsed / 60)}:${String(Math.floor(elapsed % 60)).padStart(2, '0')}`;
  let done = 0, total = 0;
  AGENTS.forEach((a, i) => {
    const p = seg(t, a.start, a.end - a.start, (x) => x);
    const finished = t >= a.end;
    total += p; if (finished) done++;
    $('agb' + i).style.width = (p * 100).toFixed(1) + '%';
    $('ags' + i).textContent = finished ? S.done : t >= a.start ? `${Math.round(p * 100)}%` : '';
    $('ags' + i).classList.toggle('on', finished);
    let note = '';
    a.notes.forEach((at, k) => { if (t >= at && !finished) note = S.agentNotes[i][k]; });
    $('agn' + i).textContent = note;
  });
  $('phase-label').textContent = S.phase(done);
  $('phase-bar').style.width = ((total / AGENTS.length) * 100).toFixed(1) + '%';
  FEED_AT.forEach((at, i) => { const li = $('fd' + i); li.style.display = t >= at ? 'grid' : 'none'; show(li, seg(t, at, 0.4, easeOut), -6); });
  // the feed shows newest first
  const feed = $('feed');
  const order = FEED_AT.map((at, i) => [at, i]).filter(([at]) => t >= at).sort((a, b) => b[0] - a[0]).map(([, i]) => $('fd' + i));
  order.forEach(li => feed.appendChild(li));
  READ_AT.forEach((at, i) => {
    const p = seg(t, at, 0.35, easeOut) * (1 - seg(t, at + 0.75, 0.45, easeInOut));
    $('cl' + (i + 1)).style.background = p > 0.01 ? `rgba(201,138,27,${(p * 0.13).toFixed(3)})` : '';
    $('ol' + (i + 1)).classList.toggle('is-reading', p > 0.3);
  });

  // findings
  [['mk1', 4, T.notes + 0.25], ['mk2', 5, T.notes + 0.4], ['mk3', 6, T.notes + 0.55]].forEach(([id, cl, at]) => {
    const p = seg(t, at, 0.35, easeOut);
    const m = $(id);
    m.style.opacity = p; m.style.transform = `scale(${lerp(0.6, 1, p)})`;
    const om = $('om' + cl);
    const adopted = (cl === 4 && t >= T.adopt1 + 0.1) || (cl === 6 && t >= T.adopt2 + 0.1);
    om.className = 'om marker ' + (adopted ? 'ok' : m.classList.contains('mid') ? 'mid' : 'hi');
    om.style.opacity = p;
    om.textContent = adopted ? '' : m.textContent;
  });
  const open1 = seg(t, T.notes + 0.1, 0.5, easeOut) * (1 - seg(t, T.swap, 0.45, easeInOut));
  const open2 = seg(t, T.swap + 0.1, 0.5, easeOut) * (1 - seg(t, T.exportPanel, 0.3, easeInOut));
  const body1 = $('nb1'), body2 = $('nb2');
  body1.style.maxHeight = (open1 * 360).toFixed(1) + 'px'; body1.style.opacity = open1;
  body2.style.maxHeight = (open2 * 400).toFixed(1) + 'px'; body2.style.opacity = open2;
  $('n1').classList.toggle('is-open', open1 > 0.05);
  $('n2').classList.toggle('is-open', open2 > 0.05);
  $('n1').classList.toggle('is-adopted', t >= T.adopt1 + 0.08);
  $('n2').classList.toggle('is-adopted', t >= T.adopt2 + 0.08);
  const redline = (id, start) => {
    const el = $(id), del = el.querySelector('del'), ins = el.querySelector('ins');
    const strike = seg(t, start + 0.1, 0.4, easeInOut), type = seg(t, start + 0.5, 0.8, (x) => x);
    del.style.backgroundSize = `${(strike * 100).toFixed(1)}% 1.5px`;
    del.style.color = strike > 0 ? 'var(--hi)' : '';
    ins.style.maxWidth = `${(type * 30).toFixed(2)}em`;
    ins.style.marginLeft = type > 0 ? '0.15em' : '0';
    ins.style.borderBottomColor = type > 0 ? '' : 'transparent';
    el.style.setProperty('--p', type);
  };
  redline('rl1', T.adopt1);
  redline('rl2', T.adopt2);
  const handled = (t >= T.adopt1 + 0.1 ? 1 : 0) + (t >= T.adopt2 + 0.1 ? 1 : 0);
  $('done-count').textContent = `${handled}/3`;
  $('done-bar').style.width = `${(handled / 3) * 100}%`;

  // export
  [[0, T.exportPanel + 0.2], [1, T.exportPanel + 0.9], [2, T.exportPanel + 1.5]].forEach(([i, at]) => $('ck' + i).classList.toggle('on', t >= at));
  const card = seg(t, T.docx + 0.25, 0.55, easeOut);
  const fc = $('file-card');
  fc.style.opacity = card; fc.style.transform = `translateY(${(1 - card) * 10}px)`;
  $('file-ok').style.opacity = seg(t, T.docx + 1.0, 0.3, easeOut);

  cursor(t);
}

window.__seek = seek;
window.__duration = DURATION;
document.fonts.ready.then(() => { seek(0); window.__ready = true; });
