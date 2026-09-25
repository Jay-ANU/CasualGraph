import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { githubRepositoryUrl } from '../config/downloads';
import useDocumentTitle from '../utils/useDocumentTitle';

const PRINCIPLES = [
  {
    title: 'Evidence before language',
    body: 'Answers are grounded in source passages and citations, so you can check why an answer says what it says, not only what it says.',
  },
  {
    title: 'Built for how analysts work',
    body: 'Plan the search, trace the evidence, check the coverage, review the result. Each step stays visible instead of disappearing behind a finished paragraph.',
  },
  {
    title: 'Structure you can reuse',
    body: 'Disclosures become a knowledge graph that makes relationships explicit, so a finding in one report can be compared with the next.',
  },
];

const Row: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="grid gap-3 border-t border-line py-10 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:gap-16">
    <h2 className="text-[17px] font-medium text-ink">{title}</h2>
    <div className="min-w-0 max-w-[40rem]">{children}</div>
  </section>
);

const About: React.FC = () => {
  useDocumentTitle('Company');
  return (
    <div className="mx-auto max-w-content px-5 pb-24 pt-14 sm:px-8 sm:pt-20">
      <div className="max-w-[52rem]">
        <h1 className="display text-balance text-[40px] leading-[1.06] sm:text-display-lg">
          We build evidence tools for ESG and risk teams.
        </h1>
        <p className="mt-6 max-w-[40rem] text-lg leading-relaxed text-ink-3">
          CausalGraph turns long-form disclosures into answers that cite their sources, relationships you can inspect,
          and knowledge graphs you can review.
        </p>
      </div>

      <div className="mt-16">
        <Row title="What we believe">
          <dl className="space-y-6">
            {PRINCIPLES.map((principle) => (
              <div key={principle.title}>
                <dt className="font-medium text-ink">{principle.title}</dt>
                <dd className="m-0 mt-1 leading-relaxed text-ink-3">{principle.body}</dd>
              </div>
            ))}
          </dl>
        </Row>

        <Row title="Where we are">
          <p className="leading-relaxed text-ink-3">
            Our product and engineering team is based in Australia and works with teams around the world.
          </p>
        </Row>

        <Row title="Open source">
          <p className="leading-relaxed text-ink-3">
            The application is developed in the open. Read the code, run it yourself or report an issue on GitHub.
          </p>
          <a
            href={githubRepositoryUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-ink hover:underline"
          >
            View the repository <ArrowUpRight className="h-3.5 w-3.5" />
          </a>
        </Row>

        <Row title="Contact">
          <p className="leading-relaxed text-ink-3">For questions, partnerships or access, write to us.</p>
          <a href="mailto:contact@causalgraph.ai" className="text-link mt-3 inline-block text-[17px] text-ink">
            contact@causalgraph.ai
          </a>
        </Row>
      </div>
    </div>
  );
};

export default About;
