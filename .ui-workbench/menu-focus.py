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
