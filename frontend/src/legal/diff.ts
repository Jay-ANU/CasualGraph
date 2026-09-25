export type DiffPart = { kind: 'same' | 'del' | 'ins'; text: string };
/** Bounded character diff for display only. The original DOCX exporter is unchanged. */
export function diffText(before: string, after: string): DiffPart[] {
  if (before === after) return [{ kind: 'same', text: before }];
  const a = Array.from(before), b = Array.from(after);
  let prefix = 0, suffix = 0;
  while (prefix < Math.min(a.length, b.length) && a[prefix] === b[prefix]) prefix++;
  while (suffix < Math.min(a.length, b.length) - prefix && a[a.length - 1 - suffix] === b[b.length - 1 - suffix]) suffix++;
  const x = a.slice(prefix, a.length - suffix), y = b.slice(prefix, b.length - suffix);
  const parts: DiffPart[] = [];
  const push = (kind: DiffPart['kind'], value: string) => {
    if (!value) return;
    const last = parts[parts.length - 1];
    if (last?.kind === kind) last.text += value; else parts.push({ kind, text: value });
  };
  push('same', a.slice(0, prefix).join(''));
  if (x.length * y.length > 120000) {
    push('del', x.join('')); push('ins', y.join(''));
  } else {
    const width = y.length + 1;
    const scores = new Uint16Array((x.length + 1) * width);
    for (let i = x.length - 1; i >= 0; i--) for (let j = y.length - 1; j >= 0; j--) {
      scores[i * width + j] = x[i] === y[j] ? 1 + scores[(i + 1) * width + j + 1] : Math.max(scores[(i + 1) * width + j], scores[i * width + j + 1]);
    }
    let i = 0, j = 0;
    while (i < x.length || j < y.length) {
      if (i < x.length && j < y.length && x[i] === y[j]) { push('same', x[i++]); j++; }
      else if (i < x.length && (j === y.length || scores[(i + 1) * width + j] >= scores[i * width + j + 1])) push('del', x[i++]);
      else push('ins', y[j++]);
    }
  }
  push('same', suffix ? a.slice(a.length - suffix).join('') : '');
  return parts;
}
