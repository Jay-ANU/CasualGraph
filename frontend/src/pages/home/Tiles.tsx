import type { COPY } from './copy';

type Copy = (typeof COPY)['zh']['capabilities'];

/** Six tiles. Each one shows a small, honest slice of the product instead of an icon. */
export default function Tiles({ copy }: { copy: Copy }) {
  const [policies, word, ask, basis, scenarios, context] = copy.tiles;
  return (
    <div className="ap-tiles">
      <article className="ap-tile is-wide" data-reveal>
        <h3>{policies.title}</h3><p>{policies.body}</p>
        <ul className="ap-rules" aria-hidden="true">
          {copy.rules.map((rule, i) => <li key={rule} style={{ '--i': i } as React.CSSProperties}><span className="ap-toggle" /><span>{rule}</span></li>)}
        </ul>
      </article>
      <article className="ap-tile" data-reveal style={{ '--d': '80ms' } as React.CSSProperties}>
        <h3>{word.title}</h3><p>{word.body}</p>
        <div className="ap-word" aria-hidden="true">
          <span className="ap-word-line" style={{ width: '82%' }} />
          <span className="ap-word-text">{copy.redline[0]}<del>{copy.redline[1]}</del><ins>{copy.redline[2]}</ins>{copy.redline[3]}</span>
          <span className="ap-word-line" style={{ width: '64%' }} />
        </div>
      </article>
      <article className="ap-tile" data-reveal>
        <h3>{ask.title}</h3><p>{ask.body}</p>
        <div className="ap-chat" aria-hidden="true"><span className="q">{copy.question}</span><span className="a">{copy.answer}</span></div>
      </article>
      <article className="ap-tile" data-reveal style={{ '--d': '80ms' } as React.CSSProperties}>
        <h3>{basis.title}</h3><p>{basis.body}</p>
        <div className="ap-cite" aria-hidden="true"><span>{copy.cite[0]}</span><span className="ok">{copy.cite[1]}</span></div>
      </article>
      <article className="ap-tile" data-reveal style={{ '--d': '160ms' } as React.CSSProperties}>
        <h3>{scenarios.title}</h3><p>{scenarios.body}</p>
        <div className="ap-scenarios" aria-hidden="true">{copy.scenarios.map(name => <span key={name}>{name}</span>)}</div>
      </article>
      <article className="ap-tile is-full" data-reveal>
        <h3>{context.title}</h3><p>{context.body}</p>
        <dl className="ap-context" aria-hidden="true">
          {copy.context.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl>
      </article>
    </div>
  );
}
