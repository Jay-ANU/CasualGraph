import React, { useState } from 'react';
import { ArrowRight, ArrowUp } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import BrandLogo from '../components/BrandLogo';
import { githubRepositoryUrl } from '../config/downloads';
import useDocumentTitle from '../utils/useDocumentTitle';

const EXAMPLE_QUESTIONS = [
  'Compare climate commitments across my reports',
  'What evidence supports the emissions targets?',
  'Find gaps in Scope 3 reporting',
];

const STEPS = [
  {
    title: 'Bring the reports',
    body: 'Upload sustainability reports as PDF, Word or plain text. Each one is split into passages, indexed for search, and read for the entities and relationships it describes.',
  },
  {
    title: 'Ask in plain language',
    body: 'Fast mode answers from the most relevant passages. Deep mode plans a search, reads further, and checks whether the evidence covers the question before it writes — each step stays visible.',
  },
  {
    title: 'Follow the relationships',
    body: 'Targets, metrics, policies and the people who oversee them become a graph you can explore. Each relationship keeps the evidence it was extracted from.',
  },
];

const EXAMPLE_SOURCES = [
  { title: 'Orbis Materials Sustainability Report 2024', where: 'p. 42' },
  { title: 'Orbis Materials Sustainability Report 2024', where: 'p. 44' },
  { title: 'Halden Foods Climate Transition Plan', where: 'p. 9' },
];

const Cite: React.FC<{ n: number }> = ({ n }) => <span className="cg-cite">{n}</span>;

export default function Home() {
  const [question, setQuestion] = useState('');
  const navigate = useNavigate();
  useDocumentTitle();
  const openQuestion = (prompt: string) => navigate(`/agent?prompt=${encodeURIComponent(prompt.trim())}`);

  return (
    <div className="bg-paper">
      <section className="mx-auto max-w-content px-5 pb-20 pt-16 sm:px-8 sm:pb-28 sm:pt-24 lg:pt-28">
        <h1 className="display max-w-[980px] text-balance text-[42px] leading-[1.04] sm:text-display-lg lg:text-display-xl">
          Answers from sustainability reports, with the page they came from.
        </h1>
        <p className="mt-6 max-w-[34rem] text-[17px] leading-relaxed text-ink-3 sm:text-lg">
          CausalGraph reads ESG disclosures, maps how claims, metrics and policies connect, and answers your
          questions with citations back to the source passage.
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
            placeholder="Ask about targets, emissions, suppliers or oversight…"
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
          <div className="section-label">Try asking</div>
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
            <h2 className="display text-display-sm sm:text-display-md">Every claim points to a passage.</h2>
            <p className="mt-5 max-w-md leading-relaxed text-ink-3">
              Answers cite the report passages they rely on. Open a citation to read the passage itself, and see
              where the reports end and general analysis begins.
            </p>
            <Link to="/agent" className="mt-7 inline-flex items-center gap-1.5 text-sm font-medium text-ink hover:gap-2.5 transition-[gap]">
              Open the research desk <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          <figure className="m-0">
            <div className="panel p-5 sm:p-7">
              <p className="ml-auto w-fit max-w-[90%] rounded-2xl bg-paper-hover px-4 py-2.5 text-[15px] text-ink">
                How credible are the Scope 2 reduction claims in these two reports?
              </p>
              <div className="cg-prose mt-6">
                <p>
                  <strong>Orbis Materials</strong> reports a 14% fall in market-based Scope 2 emissions against 2021,
                  attributed to renewable electricity contracts at eleven sites <Cite n={1} />. Its Scope 3 category 1
                  figure is spend-based, so year-on-year changes may reflect purchasing volume rather than supplier
                  progress <Cite n={2} />.
                </p>
                <p>
                  <strong>Halden Foods</strong> sets a 42% absolute reduction target for Scope 1 and 2 by 2030{' '}
                  <Cite n={3} />, but does not disclose interim progress. Neither report gives location-based figures,
                  which makes the two claims hard to compare.
                </p>
              </div>
              <div className="mt-6 border-t border-line pt-4">
                <div className="section-label mb-2">Sources</div>
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
            <figcaption className="mt-3 text-xs text-ink-4">Example answer. The companies and figures are fictional.</figcaption>
          </figure>
        </div>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto max-w-content px-5 py-20 sm:px-8 sm:py-24">
          <h2 className="display text-display-sm sm:text-display-md">How it works</h2>
          <dl className="mt-10 border-t border-line">
            {STEPS.map((step) => (
              <div key={step.title} className="grid gap-2 border-b border-line py-6 md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] md:gap-16">
                <dt className="text-[17px] font-medium text-ink">{step.title}</dt>
                <dd className="m-0 max-w-[38rem] leading-relaxed text-ink-3">{step.body}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link to="/agent" className="btn btn-primary">Open the research desk</Link>
            <Link to="/causal-inference" className="btn btn-secondary">Explore the graph</Link>
          </div>
        </div>
      </section>

      <section className="border-t border-line bg-paper-sunken">
        <div className="mx-auto flex max-w-content flex-col gap-6 px-5 py-14 sm:px-8 md:flex-row md:items-center md:justify-between">
          <div className="max-w-xl">
            <h2 className="text-lg font-medium text-ink">CausalGraph Pet for Mac</h2>
            <p className="mt-1.5 leading-relaxed text-ink-3">
              A small desktop assistant. Drop a report or a screenshot on it and ask a question without leaving what
              you are working on.
            </p>
          </div>
          <Link to="/desktop" className="btn btn-secondary shrink-0 self-start md:self-auto">
            Download for macOS
          </Link>
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
            <Link to="/causal-inference" className="hover:text-ink">Graph</Link>
            <Link to="/desktop" className="hover:text-ink">Desktop</Link>
            <Link to="/about" className="hover:text-ink">Company</Link>
            <a href={githubRepositoryUrl} target="_blank" rel="noreferrer" className="hover:text-ink">GitHub</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
