import type { Capabilities, Catalog, Contract, ReviewTier } from './types';
import { availableTiers, TIER_LABEL } from './labels';
import { ScenarioPicker } from './ScenarioPicker';
import { PartyPicker } from './PartyPicker';
import { transactionAmount } from './transactionInput';
import { ModelSelect, Spinner } from './ui';

export type SetupValues = {
  contractType: string; ourRole: string; ourPartyBlock: string; ourPartyQuote: string; instructions: string;
  performanceStage: string; attachmentsStatus: string; businessPriority: string; dealValue: string; currency: string; date: string;
  reviewTier: ReviewTier; modelId: string; consent: boolean;
};

type Props = {
  contract: Contract; caps: Capabilities | null; catalog: Catalog | null; values: SetupValues;
  hasReview: boolean; busy: boolean; modelsLoading: boolean;
  canStart: boolean; startIssue: string;
  onType: (type: string) => void; onChange: (patch: Partial<SetupValues>) => void;
  onConsent: (value: boolean) => void; onRefreshModels: () => void; onStart: () => void; onBack?: () => void;
};

/** Everything a review needs, top to bottom; any change withdraws the model-processing consent. */
export function SetupForm(p: Props) {
  const v = p.values, off = p.busy;
  const tiers = availableTiers(p.caps);
  const amount = transactionAmount(v.dealValue);
  return <section className="lv-rail-panel" aria-labelledby="legal-setup-title">
    <div className="lv-rail-head lv-rail-head-row">
      <h2 id="legal-setup-title">审查设置</h2>
      {p.onBack && <button className="lv-text-button" onClick={p.onBack}>返回审查结果</button>}
    </div>
    <div className="lv-rail-body lv-form">
      <ScenarioPicker catalog={p.caps?.scenario_catalog} type={v.contractType} role={v.ourRole} disabled={off} onType={p.onType} onRole={ourRole => p.onChange({ ourRole })} />
      <div className="lv-field">
        <div className="lv-field-label">我方主体<span className="lv-field-aside">也可在正文中点选</span></div>
        <PartyPicker blocks={p.contract.blocks} blockId={v.ourPartyBlock} quote={v.ourPartyQuote} disabled={off}
          onChange={(ourPartyBlock, ourPartyQuote) => p.onChange({ ourPartyBlock, ourPartyQuote })} />
      </div>
      <fieldset className="lv-field lv-fieldset" disabled={off}>
        <legend className="lv-field-label">审查档位</legend>
        <div className="lv-segmented" role="radiogroup" aria-label="审查档位" style={{ gridTemplateColumns: `repeat(${tiers.length}, minmax(0, 1fr))` }}>
          {tiers.map(tier => <label key={tier.value} className={v.reviewTier === tier.value ? 'selected' : ''}>
            <input type="radio" name="legal-review-tier" value={tier.value} aria-label={TIER_LABEL[tier.value]}
              checked={v.reviewTier === tier.value} onChange={() => p.onChange({ reviewTier: tier.value })} />
            {tier.title}
          </label>)}
        </div>
        <p className="lv-hint" key={v.reviewTier}>{tiers.find(t => t.value === v.reviewTier)?.note}</p>
      </fieldset>
      <label className="lv-field"><span className="lv-field-label">审查重点<span className="lv-optional">选填</span></span>
        <textarea className="lv-textarea" aria-label="审查重点" maxLength={1500} rows={2} value={v.instructions} disabled={off}
          onChange={e => p.onChange({ instructions: e.target.value })} placeholder="如：付款节点、验收标准、违约责任" /></label>
      <details className="lv-disclosure">
        <summary>交易信息（选填）</summary>
        <div className="lv-disclosure-body">
          <div className="lv-grid-2">
            <label className="lv-field"><span className="lv-field-label">履行阶段</span>
              <select className="lv-select" aria-label="履行阶段" value={v.performanceStage} disabled={off} onChange={e => p.onChange({ performanceStage: e.target.value })}>
                <option>未知</option><option>拟签署</option><option>谈判中</option><option>已签署未履行</option><option>履行中</option><option>发生争议</option>
              </select></label>
            <label className="lv-field"><span className="lv-field-label">附件情况</span>
              <select className="lv-select" aria-label="关键附件状态" value={v.attachmentsStatus} disabled={off} onChange={e => p.onChange({ attachmentsStatus: e.target.value })}>
                <option>未知</option><option>已提供全部关键附件</option><option>存在未提供附件</option><option>无附件</option>
              </select></label>
            <label className="lv-field"><span className="lv-field-label">审查侧重</span>
              <select className="lv-select" aria-label="业务优先级" value={v.businessPriority} disabled={off} onChange={e => p.onChange({ businessPriority: e.target.value })}>
                <option>综合审查</option><option>付款与回款</option><option>交付与验收</option><option>责任限制</option><option>退出与解除</option><option>知识产权</option><option>保密与数据</option>
              </select></label>
            <label className="lv-field"><span className="lv-field-label">交易日期</span>
              <input className="lv-input" type="date" value={v.date} disabled={off} onChange={e => p.onChange({ date: e.target.value })} /></label>
            <label className="lv-field lv-span-2"><span className="lv-field-label">交易金额</span>
              <span className="lv-money">
                <input className="lv-input" aria-label="交易金额" type="text" inputMode="decimal" maxLength={16} value={v.dealValue} disabled={off} onChange={e => p.onChange({ dealValue: e.target.value })} />
                <select className="lv-select" aria-label="交易币种" value={v.currency} disabled={off} onChange={e => p.onChange({ currency: e.target.value })}>
                  <option>CNY</option><option>USD</option><option>EUR</option><option>HKD</option><option>OTHER</option>
                </select>
              </span></label>
          </div>
          {!amount.valid && <p className="lv-note is-warn" role="alert">金额格式有误：仅支持数字，最多两位小数。</p>}
        </div>
      </details>
      <div className="lv-model-box">
        <span className="lv-model-label">审查模型</span>
        <ModelSelect catalog={p.catalog} value={v.modelId} loading={p.modelsLoading} disabled={off} onChange={modelId => p.onChange({ modelId })} onRefresh={p.onRefreshModels} />
      </div>
    </div>
    <div className="lv-rail-foot lv-stack">
      <label className="lv-check"><input type="checkbox" checked={v.consent} disabled={off} onChange={e => p.onConsent(e.target.checked)} />
        <span>同意将脱敏后的合同文本、审查重点及适用的公司规范经 YData 网关提交所选模型分析</span></label>
      <div className="lv-submit-row">
        <button aria-describedby={p.startIssue ? 'legal-start-help' : undefined} className="lv-primary lv-start" disabled={!p.canStart} onClick={p.onStart}>
          {p.busy && <Spinner />}{p.hasReview ? '重新审查' : '开始审查'}
        </button>
        {p.startIssue && <span id="legal-start-help" className="lv-start-help">{p.startIssue}</span>}
      </div>
    </div>
  </section>;
}
