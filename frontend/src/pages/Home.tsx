import React, { useState } from 'react';
import { ArrowRight, ArrowUp } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import BrandLogo from '../components/BrandLogo';
import useDocumentTitle from '../utils/useDocumentTitle';

const EXAMPLE_QUESTIONS = [
  '这份合同里有哪些对我方不利的条款？',
  '付款条件和违约责任分别是怎么约定的？',
  '列出合同中的关键日期和期限',
];

const STEPS = [
  {
    title: '上传合同',
    body: '支持 PDF、Word 和纯文本。每份合同被切分为段落并建立索引，便于检索和引用。',
  },
  {
    title: '直接提问',
    body: '快速模式根据最相关的段落作答；深度模式会先规划检索、多读一些原文，并检查证据是否足以回答问题，每一步都可以查看。',
  },
  {
    title: '核对出处',
    body: '回答中的每个引用都能打开，直接阅读对应的合同原文，确认之后再使用结论。',
  },
];

const EXAMPLE_SOURCES = [
  { title: '设备采购合同（示例）', where: '第 8.2 条' },
  { title: '设备采购合同（示例）', where: '第 9.1 条' },
  { title: '技术服务协议（示例）', where: '第 12.3 条' },
];

const GITHUB_REPOSITORY_URL = 'https://github.com/Jay-ANU/CasualGraph';

const Cite: React.FC<{ n: number }> = ({ n }) => <span className="cg-cite">{n}</span>;

export default function Home() {
  const [question, setQuestion] = useState('');
  const navigate = useNavigate();
  useDocumentTitle('合同逐条审阅 agent');
  const openQuestion = (prompt: string) => navigate(`/agent?prompt=${encodeURIComponent(prompt.trim())}`);

  return (
    <div className="bg-paper">
      <section className="mx-auto max-w-content px-5 pb-20 pt-16 sm:px-8 sm:pb-28 sm:pt-24 lg:pt-28">
        <h1 className="display max-w-[980px] text-balance text-[42px] leading-[1.04] sm:text-display-lg lg:text-display-xl">
          合同逐条审阅 agent
        </h1>
        <p className="mt-6 max-w-[34rem] text-[17px] leading-relaxed text-ink-3 sm:text-lg">
          上传合同后直接提问。CausalGraph 在合同原文中查找相关条款，每个回答都附上出处，方便逐条核对。
        </p>

        <form
          className="mt-10 flex max-w-[40rem] items-center gap-2 rounded-xl border border-line-strong bg-white p-1.5 pl-4 shadow-sm transition-[border-color,box-shadow] focus-within:border-ink-4 focus-within:shadow-md"
          onSubmit={(event) => {
            event.preventDefault();
            if (question.trim()) openQuestion(question);
          }}
        >
          <input
            aria-label="Ask a research question"
            placeholder="例如：违约责任条款对我方是否公平？"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={2000}
            className="h-10 min-w-0 flex-1 bg-transparent text-[16px] text-ink outline-none placeholder:text-ink-5"
          />
          <button
            type="submit"
            aria-label="Start research"
            disabled={!question.trim()}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-ink text-white transition-colors hover:bg-ink-2 disabled:cursor-not-allowed disabled:bg-paper-hover disabled:text-ink-5"
          >
            <ArrowUp className="h-[18px] w-[18px]" />
          </button>
        </form>

        <div className="mt-5 max-w-[40rem]">
          <div className="section-label">可以这样问</div>
          <ul className="mt-2 space-y-1">
            {EXAMPLE_QUESTIONS.map((prompt) => (
              <li key={prompt}>
                <button
                  type="button"
                  onClick={() => openQuestion(prompt)}
                  className="group inline-flex items-center gap-2 py-0.5 text-left text-[15px] text-ink-3 transition-colors hover:text-ink"
                >
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 text-ink-5 transition-colors group-hover:text-ink" />
                  {prompt}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto grid max-w-content gap-10 px-5 py-20 sm:px-8 sm:py-24 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
          <div className="lg:pt-2">
            <h2 className="display text-display-sm sm:text-display-md">每个结论都指向原文。</h2>
            <p className="mt-5 max-w-md leading-relaxed text-ink-3">
              回答会引用它所依据的合同段落。打开引用即可阅读原文，也能分清哪些内容来自合同、哪些是一般性分析。
            </p>
            <Link to="/agent" className="mt-7 inline-flex items-center gap-1.5 text-sm font-medium text-ink hover:gap-2.5 transition-[gap]">
              打开工作台 <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <figure className="m-0">
            <div className="panel p-5 sm:p-7">
              <p className="ml-auto w-fit max-w-[90%] rounded-2xl bg-paper-hover px-4 py-2.5 text-[15px] text-ink">
                这两份合同的违约责任约定有什么不同？
              </p>
              <div className="cg-prose mt-6">
                <p>
                  <strong>设备采购合同</strong>约定卖方逾期交货的，每逾期一日按合同总价的 0.5‰ 支付违约金，累计不超过合同总价的
                  5% <Cite n={1} />；买方逾期付款的违约金按同一比例计算，但没有约定上限 <Cite n={2} />。
                </p>
                <p>
                  <strong>技术服务协议</strong>把双方的赔偿责任总额限制在已支付的服务费以内，并排除间接损失 <Cite n={3} />。
                  两份合同的违约金计算基础不同，直接比较前需要先统一口径。
                </p>
              </div>
              <div className="mt-6 border-t border-line pt-4">
                <div className="section-label mb-2">出处</div>
                <ol className="space-y-1.5 text-sm">
                  {EXAMPLE_SOURCES.map((source, index) => (
                    <li key={`${source.title}-${source.where}`} className="flex min-w-0 items-baseline gap-3">
                      <span className="w-4 shrink-0 font-mono text-xs text-ink-4">{index + 1}</span>
                      <span className="truncate text-ink-2">{source.title}</span>
                      <span className="shrink-0 font-mono text-xs text-ink-4">{source.where}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
            <figcaption className="mt-3 text-xs text-ink-4">示例回答，合同与数字均为虚构。</figcaption>
          </figure>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto max-w-content px-5 py-20 sm:px-8 sm:py-24">
          <h2 className="display text-display-sm sm:text-display-md">工作方式</h2>
          <dl className="mt-10 border-t border-line">
            {STEPS.map((step) => (
              <div key={step.title} className="grid gap-2 border-b border-line py-6 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-16">
                <dt className="text-[17px] font-medium text-ink">{step.title}</dt>
                <dd className="m-0 max-w-[38rem] leading-relaxed text-ink-3">{step.body}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link to="/agent" className="btn btn-primary">打开工作台</Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-content flex-col gap-6 px-5 py-10 text-sm sm:px-8 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3 text-ink-4">
            <BrandLogo size="sm" showText={false} />
            <span>CausalGraph · Built in Australia</span>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-2 text-ink-3" aria-label="Footer">
            <Link to="/agent" className="hover:text-ink">Research desk</Link>
            <a href={GITHUB_REPOSITORY_URL} target="_blank" rel="noreferrer" className="hover:text-ink">GitHub</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
