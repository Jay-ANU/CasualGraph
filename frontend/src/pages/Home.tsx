import { useState } from 'react';
import { ArrowDown, ArrowRight, Check, FileCheck2, Fingerprint, GitCompare, Lock, ShieldCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import BrandLogo from '../components/BrandLogo';
import { useI18n } from '../i18n/useI18n';
import LegalMotion from '../motion/LegalMotion';
import useDocumentTitle from '../utils/useDocumentTitle';
import './LegalHome.css';

const SCENES = [
  { id: 'purchase', label: '采购合同', topic: '交付与验收', before: '验收标准由甲方另行确定。', after: '验收标准及异议期限应由双方书面确认。', note: '把单方决定，改为双方确认。' },
  { id: 'service', label: '服务合同', topic: '服务范围', before: '乙方应提供甲方要求的其他服务。', after: '新增服务的范围、费用与期限，应由双方另行书面约定。', note: '把模糊义务，写成清晰边界。' },
  { id: 'sales', label: '销售合同', topic: '付款安排', before: '甲方在内部审批完成后支付款项。', after: '双方应约定明确的付款期限与付款条件。', note: '把不确定等待，改为明确约定。' },
  { id: 'nda', label: '保密协议', topic: '保密边界', before: '一切相关信息均属于保密信息。', after: '双方应明确保密信息范围、例外情形及保密期限。', note: '让需要保护的内容，有明确范围。' },
];
const STEPS = [
  { icon: Fingerprint, name: '先检查隐私', detail: '上传后核对脱敏结果。模型分析前，另行确认授权。' },
  { icon: ShieldCheck, name: '再确认立场', detail: '选择我方身份、合同场景和交易背景，让审查有明确方向。' },
  { icon: GitCompare, name: '逐条看清风险', detail: '回到合同原文，查看风险、依据和修改建议，而不只读一份摘要。' },
  { icon: FileCheck2, name: '由你决定修改', detail: '逐项采纳、保留或编辑；完成核验后，导出带修订痕迹的 Word。' },
];

export default function Home() {
  const { t, locale } = useI18n();
  const [sceneId, setSceneId] = useState('purchase');
  const scene = SCENES.find(item => item.id === sceneId)!;
  useDocumentTitle(t('法务 Agent · 合同审查'));
  return <div className="cg-legal-home" lang={locale}>
    <section className="cg-hero" aria-labelledby="cg-hero-title">
      <div className="cg-hero-inner">
        <div className="cg-hero-copy">
          <p className="cg-eyebrow"><span />{t('CAUSALGRAPH / 法务 Agent')}</p>
          <h1 id="cg-hero-title">{t('让每一份合同，')}<br /><em>{t('签得更有底气。')}</em></h1>
          <p className="cg-hero-description">{t('从隐私核对到逐条审查，把风险、依据与修改建议放回原文。最后的决定，始终由你作出。')}</p>
          <div className="cg-hero-actions">
            <Link to="/legal" className="cg-cta">{t('开始审查合同')}<ArrowRight size={17} /></Link>
            <a href="#legal-workflow" className="cg-text-link">{t('看看如何工作')}<ArrowDown size={15} /></a>
          </div>
          <p className="cg-hero-small"><Lock size={12} aria-hidden="true" />{t('先核对脱敏，再授权模型分析')}</p>
        </div>
        <div className="cg-hero-visual">
          <LegalMotion />
          <div className="cg-evidence-tag"><span className="cg-tag-icon"><Check size={13} /></span><div>{t('看得见原文')}<small>{t('每一条意见，都有上下文')}</small></div></div>
          <div className="cg-human-tag"><span className="cg-tag-icon"><Fingerprint size={16} /></span><div>{t('决定权在你')}<small>{t('逐项确认，而非自动改写')}</small></div></div>
        </div>
      </div>
      <div className="cg-hero-bottom"><span>{t('为真实的合同工作而设计')}</span><span>{t('采购 / 销售 / 服务 / 保密及更多场景')}</span><a href="#legal-workflow" aria-label={t('了解合同审查流程')}><ArrowDown size={16} /></a></div>
    </section>

    <section className="cg-workflow cg-home-section" id="legal-workflow" aria-labelledby="workflow-title">
      <div className="cg-section-heading"><p className="cg-eyebrow">{t('从上传，到交付')}</p><h2 id="workflow-title">{t('复杂的合同，清楚地处理。')}</h2><p>{t('不用在聊天记录里翻找结论。每一步，都知道接下来该做什么。')}</p></div>
      <div className="cg-steps">{STEPS.map((step, index) => <article key={step.name} className="cg-step">
        <div className="cg-step-top"><span>0{index+1}</span><step.icon size={23} strokeWidth={1.25} /></div>
        <h3>{t(step.name)}</h3><p>{t(step.detail)}</p><span className="cg-step-rule" aria-hidden="true" />
      </article>)}</div>
    </section>

    <section className="cg-example-section" aria-labelledby="example-title">
      <div className="cg-home-section cg-example-inner">
        <div className="cg-example-copy"><p className="cg-eyebrow">{t('不止是一份风险摘要')}</p>
          <h2 id="example-title">{t('看清问题，')}<br /><em>{t('再落到每一个字。')}</em></h2>
          <p>{t('原文、风险与建议并排呈现。你可以追问依据，也可以保留原文、手动编辑，按自己的判断推进。')}</p>
          <div className="cg-scenario-tabs" role="group" aria-label={t('合同场景示例')}>{SCENES.map(item => <button key={item.id} type="button" aria-pressed={item.id === sceneId} onClick={() => setSceneId(item.id)}>{t(item.label)}</button>)}</div>
          <p className="cg-demo-note">{t('以下仅为交互示例，不是针对具体合同的法律意见。')}</p>
        </div>
        <figure className="cg-review-demo">
          <div className="cg-demo-bar"><span><i />{t('逐条审查')}</span><span>{t('交互示例')}</span></div>
          <div className="cg-demo-paper" key={scene.id}>
            <div className="cg-demo-doc"><FileCheck2 size={17} /><span>{t(scene.label)}</span><small>04</small></div>
            <h3>{t(scene.topic)}</h3><p className="cg-original-label">{t('原条款')}</p><blockquote>{t(scene.before)}</blockquote>
            <div className="cg-revision"><span><Sparkles size={13} />{t('修改方向')}</span><p>{t(scene.after)}</p></div>
            <div className="cg-demo-insight"><span />{t(scene.note)}</div>
          </div>
          <figcaption><Fingerprint size={14} /><span>{t('实际审查中，修改建议需由你逐项确认。')}</span></figcaption>
        </figure>
      </div>
    </section>

    <section className="cg-home-section cg-trust" aria-labelledby="trust-title">
      <div><p className="cg-eyebrow">{t('谨慎，不妨碍高效')}</p><h2 id="trust-title">{t('让 AI 做协助，')}<br />{t('让专业判断留在人手中。')}</h2></div>
      <div className="cg-trust-details"><article><Lock size={20} /><div><h3>{t('授权有边界')}</h3><p>{t('原件处理与模型分析分别确认。切换模型，也需要重新确认授权。')}</p></div></article>
        <article><GitCompare size={20} /><div><h3>{t('修改可追溯')}</h3><p>{t('保留原文与修订对照，不覆盖原文件，也不会替你签署合同。')}</p></div></article>
        <article><ShieldCheck size={20} /><div><h3>{t('未确认，不装作确定')}</h3><p>{t('待核实的依据、缺失的交易信息和未完成的审查，分别展示。')}</p></div></article></div>
    </section>
    <section className="cg-home-cta"><div><p className="cg-eyebrow">{t('下一份合同，从这里开始')}</p><h2>{t('把时间，留给真正需要判断的事。')}</h2></div><Link to="/legal" className="cg-cta">{t('进入法务工作台')}<ArrowRight size={17} /></Link></section>
    <footer className="cg-home-footer"><Link to="/" aria-label={t('返回首页')}><BrandLogo size="sm" /></Link><p>{t('审查结果仅供参考，不构成法律意见。')}</p><nav aria-label={t('页脚导航')}><Link to="/agent">{t('研究工作台')}</Link><Link to="/desktop">{t('桌面应用')}</Link><Link to="/about">{t('关于我们')}</Link></nav></footer>
  </div>;
}
