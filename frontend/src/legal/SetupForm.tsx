import type { Capabilities, Catalog, Contract, ReviewTier } from './types';
import { availableTiers, tierLabel } from './labels';
import { ScenarioPicker } from './ScenarioPicker';
import { PartyPicker } from './PartyPicker';
import { transactionAmount } from './transactionInput';
import { ModelSelect, Spinner } from './ui';
import { useI18n } from '../i18n/core';

const STAGES = ['未知', '拟签署', '谈判中', '已签署未履行', '履行中', '发生争议'];
const ATTACHMENTS = ['未知', '已提供全部关键附件', '存在未提供附件', '无附件'];
const PRIORITIES = ['综合审查', '付款与回款', '交付与验收', '责任限制', '退出与解除', '知识产权', '保密与数据'];

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
  const { tx, t } = useI18n();
  const v = p.values, off = p.busy;
  // The Chinese value is what the API receives; only the visible label is translated.
  const option = (value: string) => <option key={value} value={value}>{t(value)}</option>;
  const tiers = availableTiers(p.caps);
  const amount = transactionAmount(v.dealValue);
  return <section className="lv-rail-panel" aria-labelledby="legal-setup-title">
    <div className="lv-rail-head lv-rail-head-row">
      <h2 id="legal-setup-title">{tx('审查设置', 'Review settings')}</h2>
      {p.onBack && <button className="lv-text-button" onClick={p.onBack}>{tx('返回审查结果', 'Back to results')}</button>}
    </div>
    <div className="lv-rail-body lv-form">
      <ScenarioPicker catalog={p.caps?.scenario_catalog} type={v.contractType} role={v.ourRole} disabled={off} onType={p.onType} onRole={ourRole => p.onChange({ ourRole })} />
      <div className="lv-field">
        <div className="lv-field-label">{tx('我方主体', 'Our party')}<span className="lv-field-aside">{tx('也可在正文中点选', 'or pick it in the text')}</span></div>
        <PartyPicker blocks={p.contract.blocks} blockId={v.ourPartyBlock} quote={v.ourPartyQuote} disabled={off}
          onChange={(ourPartyBlock, ourPartyQuote) => p.onChange({ ourPartyBlock, ourPartyQuote })} />
      </div>
      <fieldset className="lv-field lv-fieldset" disabled={off}>
        <legend className="lv-field-label">{tx('审查档位', 'Review depth')}</legend>
        <div className="lv-segmented" role="radiogroup" aria-label={tx('审查档位', 'Review depth')} style={{ gridTemplateColumns: `repeat(${tiers.length}, minmax(0, 1fr))` }}>
          {tiers.map(tier => <label key={tier.value} className={v.reviewTier === tier.value ? 'selected' : ''}>
            <input type="radio" name="legal-review-tier" value={tier.value} aria-label={tierLabel(tier.value)}
              checked={v.reviewTier === tier.value} onChange={() => p.onChange({ reviewTier: tier.value })} />
            {tier.title}
          </label>)}
        </div>
        <p className="lv-hint" key={v.reviewTier}>{tiers.find(t => t.value === v.reviewTier)?.note}</p>
      </fieldset>
      <label className="lv-field"><span className="lv-field-label">{tx('审查重点', 'Review focus')}<span className="lv-optional">{tx('选填', 'optional')}</span></span>
        <textarea className="lv-textarea" aria-label={tx('审查重点', 'Review focus')} maxLength={1500} rows={2} value={v.instructions} disabled={off}
          onChange={e => p.onChange({ instructions: e.target.value })} placeholder={tx('如：付款节点、验收标准、违约责任', 'e.g. payment milestones, acceptance criteria, liability for breach')} /></label>
      <details className="lv-disclosure">
        <summary>{tx('交易信息（选填）', 'Transaction details (optional)')}</summary>
        <div className="lv-disclosure-body">
          <div className="lv-grid-2">
            <label className="lv-field"><span className="lv-field-label">{tx('履行阶段', 'Performance stage')}</span>
              <select className="lv-select" aria-label={tx('履行阶段', 'Performance stage')} value={v.performanceStage} disabled={off} onChange={e => p.onChange({ performanceStage: e.target.value })}>
                {STAGES.map(option)}
              </select></label>
            <label className="lv-field"><span className="lv-field-label">{tx('附件情况', 'Attachments')}</span>
              <select className="lv-select" aria-label={tx('关键附件状态', 'Key attachments')} value={v.attachmentsStatus} disabled={off} onChange={e => p.onChange({ attachmentsStatus: e.target.value })}>
                {ATTACHMENTS.map(option)}
              </select></label>
            <label className="lv-field"><span className="lv-field-label">{tx('审查侧重', 'Business priority')}</span>
              <select className="lv-select" aria-label={tx('业务优先级', 'Business priority')} value={v.businessPriority} disabled={off} onChange={e => p.onChange({ businessPriority: e.target.value })}>
                {PRIORITIES.map(option)}
              </select></label>
            <label className="lv-field"><span className="lv-field-label">{tx('交易日期', 'Transaction date')}</span>
              <input className="lv-input" type="date" value={v.date} disabled={off} onChange={e => p.onChange({ date: e.target.value })} /></label>
            <label className="lv-field lv-span-2"><span className="lv-field-label">{tx('交易金额', 'Transaction amount')}</span>
              <span className="lv-money">
                <input className="lv-input" aria-label={tx('交易金额', 'Transaction amount')} type="text" inputMode="decimal" maxLength={16} value={v.dealValue} disabled={off} onChange={e => p.onChange({ dealValue: e.target.value })} />
                <select className="lv-select" aria-label={tx('交易币种', 'Currency')} value={v.currency} disabled={off} onChange={e => p.onChange({ currency: e.target.value })}>
                  <option>CNY</option><option>USD</option><option>EUR</option><option>HKD</option><option>OTHER</option>
                </select>
              </span></label>
          </div>
          {!amount.valid && <p className="lv-note is-warn" role="alert">{tx('金额格式有误：仅支持数字，最多两位小数。', 'Enter the amount as digits, with at most two decimal places.')}</p>}
        </div>
      </details>
      <div className="lv-model-box">
        <span className="lv-model-label">{tx('审查模型', 'Model')}</span>
        <ModelSelect catalog={p.catalog} value={v.modelId} loading={p.modelsLoading} disabled={off} onChange={modelId => p.onChange({ modelId })} onRefresh={p.onRefreshModels} />
      </div>
    </div>
    <div className="lv-rail-foot lv-stack">
      <label className="lv-check"><input type="checkbox" checked={v.consent} disabled={off} onChange={e => p.onConsent(e.target.checked)} />
        <span>{tx('同意将脱敏后的合同文本、审查重点及适用的公司规范经 YData 网关提交所选模型分析',
          'I agree to send the redacted contract, my review focus and the applicable company policies to the selected model through the YData gateway')}</span></label>
      <div className="lv-submit-row">
        <button aria-describedby={p.startIssue ? 'legal-start-help' : undefined} className="lv-primary lv-start" disabled={!p.canStart} onClick={p.onStart}>
          {p.busy && <Spinner />}{p.hasReview ? tx('重新审查', 'Review again') : tx('开始审查', 'Start review')}
        </button>
        {p.startIssue && <span id="legal-start-help" className="lv-start-help">{p.startIssue}</span>}
      </div>
    </div>
  </section>;
}
