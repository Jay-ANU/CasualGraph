import { useState } from 'react';
import { Lock, ShieldCheck, Upload, UserCheck } from 'lucide-react';
import type { Capabilities } from './types';
import { STEPS } from './labels';
import { ic } from './icon';

const STEP_NOTES = ['确认公司名称、联系人、账户等已替换为代号', '选择合同类型，说明你代表哪一方', '看清风险、依据和改法，逐条决定', '下载审查报告；Word 合同可导出修订稿'];

export function Welcome({ caps, disabled, instructions, contractType, onUpload, onDrop, onInstructions, onScenario }: {
  caps: Capabilities | null; disabled: boolean; instructions: string; contractType: string;
  onUpload: () => void; onDrop: (files: FileList) => void;
  onInstructions: (value: string) => void; onScenario: (type: string) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const scenes = caps?.scenario_catalog?.scenarios.filter(s => ['采购合同', '销售合同', '服务合同', '租赁合同', '保密协议'].includes(s.label)) || [];
  return <main id="legal-main" tabIndex={-1} className="lv-welcome">
    <div className="lv-welcome-inner">
      <h1>签字之前，先把合同看明白</h1>
      <p className="lv-lede">上传一份合同，逐条看清哪些条款对你不利、为什么、可以怎么改。改不改，由你决定。</p>

      <section className={`lv-upload ${dragging ? 'is-dragging' : ''}`} aria-label="上传合同"
        onDragOver={e => { e.preventDefault(); if (!disabled && e.dataTransfer.types.includes('Files')) setDragging(true); }}
        onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
        onDrop={e => { e.preventDefault(); setDragging(false); if (!disabled) onDrop(e.dataTransfer.files); }}>
        <div className="lv-upload-main">
          <div>
            <h2>{dragging ? '松开鼠标，上传这份合同' : '上传合同'}</h2>
            <p>支持 Word（.docx）、可复制文字的 PDF 和 TXT，单个文件不超过 10 MB。</p>
          </div>
          <div className="lv-upload-actions">
            <button type="button" className="lv-primary lv-upload-cta" disabled={disabled} onClick={onUpload} aria-label="选择一份合同开始"><Upload {...ic} />选择文件</button>
            <span>或把文件拖到这里</span>
          </div>
        </div>
        <ul className="lv-assurances" aria-label="隐私保护">
          <li><ShieldCheck {...ic} /><div><strong>自动脱敏</strong><span>公司名称、联系人、账户等会替换成代号，遗漏的可以手动补充</span></div></li>
          <li><Lock {...ic} /><div><strong>加密保存</strong><span>原件上传到服务器解析，加密保存</span></div></li>
          <li><UserCheck {...ic} /><div><strong>发送前征得同意</strong><span>只有你确认后，脱敏正文才会发送给 AI 模型</span></div></li>
        </ul>
      </section>

      <ol className="lv-howto" aria-label="审查流程">
        {STEPS.map((step, i) => <li key={step}><span className="lv-howto-index">{i + 1}</span><strong>{step}</strong><p>{STEP_NOTES[i]}</p></li>)}
      </ol>

      <section className="lv-prefs" aria-label="可选审查偏好">
        <div className="lv-prefs-head"><h2>先说说情况</h2><span>可选，上传后也能修改</span></div>
        {scenes.length > 0 && <div className="lv-type-chips" role="group" aria-label="常用合同类型">
          {scenes.map(scene => <button type="button" key={scene.id} aria-pressed={scene.label === contractType} className={scene.label === contractType ? 'selected' : ''} onClick={() => onScenario(scene.label)}>{scene.label}</button>)}
          <span className="lv-type-more">共 {caps?.scenario_catalog?.scenarios.length} 类，其他类型上传后选择</span>
        </div>}
        <label className="lv-field-label" htmlFor="legal-focus">你最担心什么？</label>
        <textarea id="legal-focus" className="lv-textarea" aria-label="审查关注点" value={instructions} maxLength={1500} rows={3} onChange={e => onInstructions(e.target.value)}
          placeholder="例如：担心先付款却收不到货，希望补充验收和退款安排。" />
      </section>

      <p className="lv-footnote">AI 辅助审查，不构成法律意见。涉及重大利益时，请咨询执业律师。</p>
    </div>
  </main>;
}
