import React from 'react';
import { ArrowUpRight, Globe, Mail } from 'lucide-react';

const principles = [
  {
    title: 'Evidence before language',
    description: 'We ground every answer in source chunks and citations—so you can audit the why, not just the what.',
  },
  {
    title: 'Analyst-grade workflows',
    description: 'Built for how analysts think: plan, trace, reflect and review with complete visibility.',
  },
  {
    title: 'Structured intelligence',
    description: 'We convert disclosures into a knowledge graph that makes relationships explicit and reusable.',
  },
];

const CompanyEvidenceSystem: React.FC = () => (
  <div className="moon-company-system" aria-label="Document evidence graph workflow">
    <div className="moon-company-doc-stage">
      <div className="moon-company-doc-card ghost-one">
        <span>Annual Report 2024</span>
        <i />
        <i />
        <i />
        <small>Page 8</small>
      </div>
      <div className="moon-company-doc-card ghost-two">
        <span>TCFD Index 2024</span>
        <i />
        <i />
        <i />
        <small>Page 1</small>
      </div>
      <div className="moon-company-doc-card primary">
        <div className="moon-doc-card-head">
          <span>Sustainability Report 2024</span>
          <b>...</b>
        </div>
        <small>Example Corp</small>
        <i className="wide" />
        <i />
        <i className="short" />
        <strong>E) Emissions</strong>
        <i className="wide" />
        <i />
        <i className="medium" />
        <em>Page 42</em>
      </div>
      <svg className="moon-company-stream-lines" viewBox="0 0 340 280" aria-hidden="true" preserveAspectRatio="none">
        {Array.from({ length: 14 }).map((_, index) => (
          <path
            key={index}
            d={`M232 ${48 + index * 12} C272 ${68 + index * 6} 296 ${110 + index * 3} 340 ${140}`}
          />
        ))}
      </svg>
    </div>

    <div className="moon-company-source-card">
      <div className="moon-source-card-head">
        <span>Source chunk</span>
        <b>...</b>
      </div>
      <small>p.42 L3-L18</small>
      <p>... Scope 3 Category 1 emissions include purchased goods and services ...</p>
    </div>

    <div className="moon-company-eclipse" />

    <div className="moon-company-network">
      <svg className="moon-company-network-lines" viewBox="0 0 680 480" aria-hidden="true">
        {/* Purchased goods -> Scope 3 Category 1 (vertical down) */}
        <path d="M170 112 L170 215" />
        {/* Purchased goods -> is part of */}
        <path d="M260 65 C295 65 318 75 335 82" />
        {/* is part of -> Scope 3 Emissions */}
        <path d="M440 90 C470 105 490 122 510 140" />
        {/* Scope 3 Category 1 -> Scope 3 Emissions (direct curve via top) */}
        <path d="M290 222 C360 200 430 168 508 142" />
        {/* Scope 3 Category 1 -> reported in (vertical) */}
        <path d="M175 268 L175 290" className="relationship-drop" />
        {/* reported in -> Sustainability Report 2024 (vertical) */}
        <path d="M175 340 L175 365" />
        {/* Scope 3 Category 1 -> Citation */}
        <path d="M290 244 C340 244 380 242 410 240" />
        {/* Scope 3 Category 1 -> Reviewed */}
        <path d="M290 258 C330 280 360 308 382 335" />
      </svg>

      <div className="moon-company-node-card purchased">
        <small>Entity</small>
        <strong>Purchased goods<br />and services</strong>
      </div>
      <div className="moon-company-node-card category">
        <strong>Scope 3 Category 1</strong>
      </div>
      <div className="moon-company-node-card document">
        <small>Document</small>
        <strong>Sustainability<br />Report 2024</strong>
      </div>
      <div className="moon-company-relation is-part">
        <small>Relationship</small>
        <strong>is part of</strong>
      </div>
      <div className="moon-company-relation reported">
        <small>Relationship</small>
        <strong>reported in</strong>
      </div>
      <div className="moon-company-node-card scope">
        <small>Entity</small>
        <strong>Scope 3<br />Emissions</strong>
      </div>
      <div className="moon-company-node-card citation">
        <small>Citation</small>
        <strong>p.42 L3-L18</strong>
        <span>↗</span>
      </div>
      <div className="moon-company-node-card review">
        <small>Review</small>
        <strong>Reviewed</strong>
        <span>By Analyst - May 14, 2025</span>
      </div>
    </div>
  </div>
);

const About: React.FC = () => (
  <div className="moon-page overflow-x-hidden">
    <section className="moon-section border-b moon-hairline">
      <div className="relative z-10 mx-auto flex min-h-[calc(100svh-81px)] max-w-page-2xl flex-col justify-start px-4 py-10 sm:px-6 lg:px-8 xl:px-12 2xl:px-16">
        <div className="mx-auto max-w-5xl text-center">
          <h1 className="font-display text-[42px] font-semibold leading-[1.02] text-white sm:text-[56px] xl:text-[66px]">
            Evidence systems for ESG and risk teams.
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-[17px] leading-7 moon-copy">
            We turn long-form disclosures into verifiable answers, inspectable relationships, and reviewable knowledge graphs.
          </p>
        </div>

        <div className="moon-company-system-frame mt-6">
          <CompanyEvidenceSystem />
        </div>
      </div>
    </section>

    <section className="mx-auto max-w-page-2xl px-4 pt-2 sm:px-6 lg:px-8 xl:px-12 2xl:px-16">
      <div className="moon-company-divider" />
      <div className="moon-company-principles">
        {principles.map((principle, index) => (
          <article key={principle.title} className="moon-company-principle">
            <div className="moon-company-principle-num">{String(index + 1).padStart(2, '0')}</div>
            <div>
              <h2>{principle.title}</h2>
              <p>{principle.description}</p>
            </div>
          </article>
        ))}
      </div>
    </section>

    <section className="mx-auto max-w-page-2xl px-4 pb-14 pt-10 sm:px-6 lg:px-8 xl:px-12 2xl:px-16">
      <div className="moon-company-contact">
        <div className="moon-company-contact-item">
          <div className="moon-company-contact-icon">
            <Mail className="h-4 w-4" />
          </div>
          <div className="moon-company-contact-body">
            <small>Get in touch</small>
            <a href="mailto:contact@causalgraph.ai">
              contact@causalgraph.ai
              <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
        <div className="moon-company-contact-item">
          <div className="moon-company-contact-icon">
            <Globe className="h-4 w-4" />
          </div>
          <div className="moon-company-contact-body">
            <small>Built in Australia</small>
            <p>Product and engineering team based in Australia, serving teams around the world.</p>
          </div>
        </div>
      </div>
    </section>
  </div>
);

export default About;
