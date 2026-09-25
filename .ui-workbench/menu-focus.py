from pathlib import Path
p=Path('frontend/src/legal/LegalDesk.tsx')
s=p.read_text()
old="      if (this.state.mobileMenu) document.getElementById('legal-close-menu')?.focus(); else this.focusBeforeMenu?.focus();"
assert old in s
s=s.replace(old, "      requestAnimationFrame(() => { if (!this.live) return; if (this.state.mobileMenu) document.getElementById('legal-close-menu')?.focus(); else this.focusBeforeMenu?.focus(); });")
old='onKeyDown={this.menuKey}>'
assert old in s
s=s.replace(old, '''onKeyDown={this.menuKey} onTransitionEnd={event => {
        if (event.target === event.currentTarget && this.state.mobileMenu && !event.currentTarget.contains(document.activeElement)) document.getElementById('legal-close-menu')?.focus();
      }}>''')
s=s.replace('<small>Word 中仍保留可接受、可拒绝的修订；请在分享前复核。</small>', '<small>{c.format === \'docx\' ? \'Word 中仍保留可接受、可拒绝的修订；请在分享前复核。\' : \'文字修改稿不是 Word 修订文件；请在分享前对照原合同复核。\'}</small>')
p.write_text(s)
p=Path('frontend/src/legal/LegalDesk.css')
s=p.read_text(); assert 'transition: transform .18s ease, visibility .18s ease;' in s
s=s.replace('transition: transform .18s ease, visibility .18s ease;', 'transition: transform .18s ease;')
p.write_text(s)
print('Fixed off-canvas visibility/focus timing without relaxing keyboard assertions')
p=Path('frontend/src/legal/LegalDesk.tsx')
lines=p.read_text().splitlines()
i=next(i for i,line in enumerate(lines) if '{r && <section className="lv-assistant-response">' in line)
header='              {r && <section className="lv-assistant-response">'
assert lines[i].startswith(header)
process=lines[i][len(header):]
lines[i]=header
j=next(i for i,line in enumerate(lines) if '<details className="lv-review-details">' in line)
lines.insert(j, '                '+process)
p.write_text('\n'.join(lines)+'\n')
p=Path('frontend/src/legal/LegalDesk.css')
s=p.read_text()
s=s.replace('padding: 15px 0; margin-top: 20px;', 'padding: 10px 0; margin-top: 12px;')
s=s.replace('.lv-export { position: sticky; bottom: -24px;', '.lv-export { position: relative; bottom: auto;')
s += '\n/* Keep the first finding ahead of execution metadata and unobscured by export controls. */\n.lv-results + .lv-assistant-label { margin-top: 28px; }\n.lv-result-summary { margin-bottom: 16px; }\n.lv-export { bottom: auto; }\n'
p.write_text(s)
print('Prioritized substantive findings and removed occluding floating export panel')
