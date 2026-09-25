import { ArrowRight, Check } from 'lucide-react';
import type { Capabilities, Catalog, Contract } from './types';
import { ScenarioPicker } from './ScenarioPicker';
import { PartyPicker } from './PartyPicker';
import { transactionAmount } from './transactionInput';
import { ModelSelect, Spinner } from './ui';
import { ic } from './icon';

export type SetupValues = {
  contractType: string; ourRole: string; ourPartyBlock: string; ourPartyQuote: string; instructions: string;
  performanceStage: string; attachmentsStatus: string; businessPriority: string; dealValue: string; currency: string; date: string;
  reviewMode: 'standard' | 'multi_agent'; modelId: string; consent: boolean;
};

type Props = {
  contract: Contract; caps: Capabilities | null; catalog: Catalog | null; values: SetupValues;
  hasReview: boolean; busy: boolean; locked: boolean; modelsLoading: boolean;
  scenarioValid: boolean; partyValid: boolean; canStart: boolean; startIssue: string;
  onType: (type: string) => void; onChange: (patch: Partial<SetupValues>) => void;
  onConsent: (value: boolean) => void; onRefreshModels: () => void; onStart: () => void;
};

const MODES: { value: SetupValues['reviewMode']; title: string; note: string }[] = [
  { value: 'multi_agent', title: '深度审查', note: '法律、商业和公司规范分别检查，再交叉复核。用时更长，模型调用更多。' },
  { value: 'standard', title: '标准审查', note: '一次完整通读检查，速度更快。' },
];

export function SetupForm(p: Props) {
  const v = p.values, off = p.busy || p.locked;
  const amount = transactionAmount(v.dealValue);
  const ready = [
    { label: '选择你的角色', done: p.scenarioValid },
    { label: '确认合同中的我方主体', done: p.partyValid },
    { label: '同意发送给 AI 模型', done: v.consent },
  ];
  return <div className="lv-setup">
    <section className="lv-form-block" aria-labelledby="legal-setup-role">
      <h3 id="legal-setup-role">这是什么合同，你是哪一方？</h3>
      <ScenarioPicker catalog={p.caps?.scenario_catalog} type={v.contractType} role={v.ourRole} disabled={off} onType={p.onType} onRole={ourRole => p.onChange({ ourRole })} />
    </section>

    <section className="lv-form-block" aria-labelledby="legal-setup-party">
      <h3 id="legal-setup-party">合同里哪一个主体是你？</h3>
      <p className="lv-hint">点选合同中代表你的一方。候选内容直接摘自原文，系统不会替你判断。</p>
      <PartyPicker blocks={p.contract.blocks} blockId={v.ourPartyBlock} quote={v.ourPartyQuote} disabled={off}
        onChange={(ourPartyBlock, ourPartyQuote) => p.onChange({ ourPartyBlock, ourPartyQuote })} />
    </section>

    <section className="lv-form-block" aria-labelledby="legal-setup-focus">
      <h3 id="legal-setup-focus">还有什么要特别关注？<span className="lv-optional">可选</span></h3>
      <textarea className="lv-textarea" aria-label="补充审查要求" maxLength={1500} rows={3} value={v.instructions} disabled={off}
        onChange={e => p.onChange({ instructions: e.target.value })} placeholder="例如：希望把付款改成验收后支付；不要填写与审查无关的敏感信息。" />
      <details className="lv-disclosure">
        <summary>补充交易背景（可选）</summary>
        <div className="lv-disclosure-body">
          <div className="lv-grid-2">
            <label className="lv-field"><span className="lv-field-label">履行阶段</span>
              <select className="lv-select" aria-label="履行阶段" value={v.performanceStage} disabled={off} onChange={e => p.onChange({ performanceStage: e.target.value })}>
                <option>未知</option><option>拟签署</option><option>谈判中</option><option>已签署未履行</option><option>履行中</option><option>发生争议</option>
              </select></label>
            <label className="lv-field"><span className="lv-field-label">关键附件</span>
              <select className="lv-select" aria-label="关键附件状态" value={v.attachmentsStatus} disabled={off} onChange={e => p.onChange({ attachmentsStatus: e.target.value })}>
                <option>未知</option><option>已提供全部关键附件</option><option>存在未提供附件</option><option>无附件</option>
              </select></label>
            <label className="lv-field"><span className="lv-field-label">本轮最关心</span>
              <select className="lv-select" aria-label="业务优先级" value={v.businessPriority} disabled={off} onChange={e => p.onChange({ businessPriority: e.target.value })}>
                <option>综合审查</option><option>付款与回款</option><option>交付与验收</option><option>责任限制</option><option>退出与解除</option><option>知识产权</option><option>保密与数据</option>
              </select></label>
            <label className="lv-field"><span className="lv-field-label">交易金额（可留空）</span>
              <span className="lv-money">
                <input className="lv-input" aria-label="交易金额" type="text" inputMode="decimal" maxLength={16} value={v.dealValue} disabled={off} onChange={e => p.onChange({ dealValue: e.target.value })} placeholder="例如 1280000" />
                <select className="lv-select" aria-label="交易币种" value={v.currency} disabled={off} onChange={e => p.onChange({ currency: e.target.value })}>
                  <option>CNY</option><option>USD</option><option>EUR</option><option>HKD</option><option>OTHER</option>
                </select>
              </span></label>
            <label className="lv-field"><span className="lv-field-label">交易日期（可留空）</span>
              <input className="lv-input" type="date" value={v.date} disabled={off} onChange={e => p.onChange({ date: e.target.value })} /></label>
          </div>
          {!amount.valid && <p className="lv-note is-warn" role="alert">请输入不带单位的数字，最多两位小数，例如 1000000.05。</p>}
          <p className="lv-hint">这些信息由你填写，仅作审查参考，不会当作合同原文。附件缺失时，依赖附件的判断会单独标出。</p>
        </div>
      </details>
    </section>

    <section className="lv-form-block" aria-labelledby="legal-setup-mode">
      <h3 id="legal-setup-mode">审查方式</h3>
      <div className="lv-option-cards" role="radiogroup" aria-label="审查方式">
        {MODES.map(mode => <label key={mode.value} className={`lv-option-card ${v.reviewMode === mode.value ? 'selected' : ''} ${off ? 'is-disabled' : ''}`}>
          <input type="radio" name="legal-review-mode" value={mode.value} aria-label={mode.title} aria-describedby={`legal-mode-${mode.value}`}
            checked={v.reviewMode === mode.value} disabled={off} onChange={() => p.onChange({ reviewMode: mode.value })} />
          <span className="lv-option-title">{mode.title}{mode.value === 'multi_agent' && <em>推荐</em>}</span>
          <span className="lv-option-note" id={`legal-mode-${mode.value}`}>{mode.note}</span>
        </label>)}
      </div>
      <div className="lv-model-row">
        <span className="lv-field-label">AI 模型</span>
        <ModelSelect catalog={p.catalog} value={v.modelId} loading={p.modelsLoading} disabled={off} onChange={modelId => p.onChange({ modelId })} onRefresh={p.onRefreshModels} />
      </div>
    </section>

    <section className="lv-start-block" aria-label="开始审查">
      <ul className="lv-ready" aria-label="开始前需要完成">
        {ready.map(item => <li key={item.label} className={item.done ? 'done' : ''}><span aria-hidden="true">{item.done ? <Check {...ic} size={12} strokeWidth={2.5} /> : null}</span>{item.label}<span className="lv-sr">{item.done ? '（已完成）' : '（未完成）'}</span></li>)}
      </ul>
      <label className="lv-check lv-consent"><input type="checkbox" checked={v.consent} disabled={off} onChange={e => p.onConsent(e.target.checked)} />
        <span>同意将脱敏后的合同正文、补充说明和适用的公司规范，经 YData 模型网关发送给所选 AI 模型分析。</span></label>
      <button aria-describedby="legal-start-help" className="lv-primary lv-start" disabled={!p.canStart} onClick={p.onStart}>
        {p.busy ? <Spinner /> : null}{p.hasReview ? '重新审查' : '开始审查'}{!p.busy && <ArrowRight {...ic} />}
      </button>
      <p id="legal-start-help" className="lv-start-help">{p.locked ? '本轮正在审查，完成后可以调整设置再审查一轮。' : p.startIssue || '准备就绪。本轮设置会记录在审查报告中。'}</p>
    </section>
  </div>;
}
