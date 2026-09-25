import type { Capabilities, Catalog, Contract } from './types';
import { ScenarioPicker } from './ScenarioPicker';
import { PartyPicker } from './PartyPicker';
import { transactionAmount } from './transactionInput';
import { FormRow, ModelSelect, Spinner } from './ui';

export type SetupValues = {
  contractType: string; ourRole: string; ourPartyBlock: string; ourPartyQuote: string; instructions: string;
  performanceStage: string; attachmentsStatus: string; businessPriority: string; dealValue: string; currency: string; date: string;
  reviewMode: 'standard' | 'multi_agent'; modelId: string; consent: boolean;
};

type Props = {
  contract: Contract; caps: Capabilities | null; catalog: Catalog | null; values: SetupValues;
  hasReview: boolean; busy: boolean; locked: boolean; modelsLoading: boolean;
  canStart: boolean; startIssue: string;
  onType: (type: string) => void; onChange: (patch: Partial<SetupValues>) => void;
  onConsent: (value: boolean) => void; onRefreshModels: () => void; onStart: () => void;
};

const MODES: { value: SetupValues['reviewMode']; title: string; note: string }[] = [
  { value: 'multi_agent', title: '深度审查', note: '法律、商业与公司规范分项审查，交叉复核' },
  { value: 'standard', title: '标准审查', note: '单轮全文审查，耗时较短' },
];

export function SetupForm(p: Props) {
  const v = p.values, off = p.busy || p.locked;
  const amount = transactionAmount(v.dealValue);
  const help = p.locked ? '审查进行中，完成后可调整设置重新审查。' : p.startIssue;
  return <div className="lv-setup">
    <ScenarioPicker catalog={p.caps?.scenario_catalog} type={v.contractType} role={v.ourRole} disabled={off} onType={p.onType} onRole={ourRole => p.onChange({ ourRole })} />
    <FormRow label="我方主体">
      <PartyPicker blocks={p.contract.blocks} blockId={v.ourPartyBlock} quote={v.ourPartyQuote} disabled={off}
        onChange={(ourPartyBlock, ourPartyQuote) => p.onChange({ ourPartyBlock, ourPartyQuote })} />
    </FormRow>
    <FormRow label="审查重点" note="选填">
      <textarea className="lv-textarea" aria-label="审查重点" maxLength={1500} rows={2} value={v.instructions} disabled={off}
        onChange={e => p.onChange({ instructions: e.target.value })} placeholder="如：付款节点、验收标准、违约责任" />
      <details className="lv-disclosure lv-disclosure-inline">
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
    </FormRow>
    <FormRow label="审查模式">
      <div className="lv-segmented-radio" role="radiogroup" aria-label="审查模式">
        {MODES.map(mode => <label key={mode.value} className={v.reviewMode === mode.value ? 'selected' : ''}>
          <input type="radio" name="legal-review-mode" value={mode.value} aria-label={mode.title}
            checked={v.reviewMode === mode.value} disabled={off} onChange={() => p.onChange({ reviewMode: mode.value })} />
          {mode.title}
        </label>)}
      </div>
      <p className="lv-hint">{MODES.find(m => m.value === v.reviewMode)?.note}</p>
    </FormRow>
    <FormRow label="审查模型">
      <ModelSelect catalog={p.catalog} value={v.modelId} loading={p.modelsLoading} disabled={off} onChange={modelId => p.onChange({ modelId })} onRefresh={p.onRefreshModels} />
    </FormRow>
    <div className="lv-submit">
      <label className="lv-check"><input type="checkbox" checked={v.consent} disabled={off} onChange={e => p.onConsent(e.target.checked)} />
        <span>同意将脱敏后的合同文本、审查重点及适用的公司规范经 YData 网关提交所选模型分析</span></label>
      <div className="lv-submit-row">
        <button aria-describedby={help ? 'legal-start-help' : undefined} className="lv-primary lv-start" disabled={!p.canStart} onClick={p.onStart}>
          {p.busy && <Spinner />}{p.hasReview ? '重新审查' : '开始审查'}
        </button>
        {help && <span id="legal-start-help" className="lv-start-help">{help}</span>}
      </div>
    </div>
  </div>;
}
