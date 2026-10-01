import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { githubRepositoryUrl } from '../config/downloads';
import { useI18n } from '../i18n/core';
import useDocumentTitle from '../utils/useDocumentTitle';

const Row: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="grid gap-3 border-t border-line py-10 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:gap-16">
    <h2 className="text-[17px] font-medium text-ink">{title}</h2>
    <div className="min-w-0 max-w-[40rem]">{children}</div>
  </section>
);

const About: React.FC = () => {
  const { tx } = useI18n();
  useDocumentTitle(tx('关于我们', 'Company'));

  const principles = [
    {
      title: tx('先脱敏，后分析', 'Redacted before analysis'),
      body: tx(
        '合同在交给任何模型之前都会先脱敏，每一处脱敏都可以对照原件核对。',
        'Contracts are redacted before any model sees them, and you can check each redaction against the original.',
      ),
    },
    {
      title: tx('分工审查，交叉复核', 'Specialists that check each other'),
      body: tx(
        '五个专业 Agent 分别负责法律风险、商业利益、公司规范、证据与覆盖复核和全文一致性，并行审查，相互检验。',
        'Five specialist agents cover legal risk, commercial interest, company policy, evidence and coverage review, and whole-contract consistency. They review in parallel and check each other’s work.',
      ),
    },
    {
      title: tx('依据在前，结论在后', 'Evidence before conclusions'),
      body: tx(
        '每条审查意见都写明依据并附上修改建议，研究工作台的回答也都引用原文出处。你看到的不只是结论，还有它从何而来。',
        'Every finding shows its basis and a suggested edit, and research answers cite their source passages. You can see why a result says what it says, not only what it says.',
      ),
    },
    {
      title: tx('最终由你决定', 'You make the call'),
      body: tx(
        '只有你采纳的修改，才会以修订痕迹写入导出的 Word 文件。审查结果仅供参考，不构成法律意见。',
        'Only the edits you accept go into the tracked-changes Word file you export. Results are for reference only and are not legal advice.',
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-14 sm:px-8 sm:pt-20">
      <div className="max-w-[52rem]">
        <h1 className="display text-balance text-[40px] leading-[1.06] sm:text-display-lg">
          {tx('我们打造有据可查的 AI 合同审查。', 'We build AI contract review that shows its work.')}
        </h1>
        <p className="mt-6 max-w-[40rem] text-lg leading-relaxed text-ink-3">
          {tx(
            '我们的法务 Agent 由一组专业 AI Agent 协同审查你的合同。我们还提供 ESG 研究工作台，把长篇披露报告转化为注明出处的回答。',
            'Our legal agent reviews your contracts with a team of specialist AI agents. We also build the ESG research desk, which turns long-form disclosures into answers that cite their sources.',
          )}
        </p>
      </div>

      <div className="mt-16">
        <Row title={tx('我们的原则', 'What we believe')}>
          <dl className="space-y-6">
            {principles.map((principle) => (
              <div key={principle.title}>
                <dt className="font-medium text-ink">{principle.title}</dt>
                <dd className="m-0 mt-1 leading-relaxed text-ink-3">{principle.body}</dd>
              </div>
            ))}
          </dl>
        </Row>

        <Row title={tx('团队所在地', 'Where we are')}>
          <p className="leading-relaxed text-ink-3">
            {tx(
              '我们的产品和工程团队位于澳大利亚，与世界各地的团队合作。',
              'Our product and engineering team is based in Australia and works with teams around the world.',
            )}
          </p>
        </Row>

        <Row title={tx('开源', 'Open source')}>
          <p className="leading-relaxed text-ink-3">
            {tx(
              '本应用以开源方式开发。你可以在 GitHub 上阅读代码、自行运行，或提交问题反馈。',
              'The application is developed in the open. Read the code, run it yourself or report an issue on GitHub.',
            )}
          </p>
          <a
            href={githubRepositoryUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-ink hover:underline"
          >
            {tx('查看代码仓库', 'View the repository')} <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </Row>

        <Row title={tx('联系我们', 'Contact')}>
          <p className="leading-relaxed text-ink-3">
            {tx('如需咨询、洽谈合作或申请使用，欢迎来信。', 'For questions, partnerships or access, write to us.')}
          </p>
          <a href="mailto:contact@causalgraph.ai" className="text-link mt-3 inline-block text-[17px] text-ink">
            contact@causalgraph.ai
          </a>
        </Row>
      </div>
    </div>
  );
};

export default About;
