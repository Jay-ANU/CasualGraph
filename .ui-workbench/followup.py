from pathlib import Path

def edit(name, old, new):
    p = Path(name)
    text = p.read_text()
    assert old in text, (name, old[:90])
    p.write_text(text.replace(old, new))

css = Path('frontend/src/legal/LegalDesk.css')
s = css.read_text()
for old, new in [('#5670a2', '#405b91'), ('#667694', '#52617e'), ('#7b8bab', '#586a8c')]:
    s = s.replace(old, new)
s += '\n.legal-v2 h1, .legal-v2 h2, .legal-v2 h3, .legal-v2 h4 { font-family: inherit; }\n'
css.write_text(s)
p = 'frontend/src/legal/LegalDesk.tsx'
edit(p, 'pendingFile: File | null; confirmingRedaction: boolean;', "exportFormat: 'docx' | 'txt' | null; pendingFile: File | null; confirmingRedaction: boolean;")
edit(p, 'pendingFile: null, confirmingRedaction: false', 'exportFormat: null, pendingFile: null, confirmingRedaction: false')
edit(p, "private download = async (format: 'docx' | 'txt' | 'md') => {", "private download = async (format: 'docx' | 'txt' | 'md', confirmed = false) => {")
edit(p, "if (format !== 'md' && !window.confirm('修订稿包含真实信息以及删除内容，不是脱敏副本。确认导出？')) return;", "if (format !== 'md' && !confirmed) { this.setState({ exportFormat: format, error: '' }); return; }")
edit(p, "this.setState({ notice: format === 'md'", "this.setState({ exportFormat: null, notice: format === 'md'")
edit(p, '!s.archivePolicy && <div', '!s.archivePolicy && !s.exportFormat && <div')
needle = '      {s.archivePolicy && <ConfirmDialog'
replacement = '''      {s.exportFormat && <ConfirmDialog title="导出前，检查文件中的敏感信息" confirmLabel="确认并导出修订稿" busy={s.busy}
        onCancel={() => this.setState({ exportFormat: null, error: '' })} onConfirm={() => { const format = s.exportFormat; if (format) void this.run(() => this.download(format, true)); }}>
        <p>这份修订稿包含真实信息和删除内容，不是脱敏副本。请确认接收人和分享范围，避免将原件中的隐私继续传播。</p>
        <p>导出不会自动签署合同，也不会覆盖你的原文件。</p>{s.error && <p role="alert">{s.error}</p>}
      </ConfirmDialog>}
''' + needle
edit(p, needle, replacement)
p = 'scripts/legal_ui_smoke.py'
edit(p, 'import functools', 'from contextlib import contextmanager\nimport functools')
edit(p, 'def audit_layout(page, label):', '''@contextmanager
def capture_failure():
    try:
        yield
    except Exception:
        try:
            page.screenshot(path=str(OUT/'failure.png'), full_page=True)
            (OUT/'failure.html').write_text(page.content(), encoding='utf-8')
        except Exception:
            pass
        raise

AXE_VIOLATIONS = []
def audit_layout(page, label):''')
edit(p, 'assert not violations, (label, violations)', 'AXE_VIOLATIONS.extend([{\'state\': label, **v} for v in violations])')
edit(p, 'with sync_playwright() as p:', 'with sync_playwright() as p, capture_failure():')
edit(p, "    elif path=='/legal/reviews/r1/export':data=review", "    elif path=='/legal/reviews/r1/export':\n        if urlparse(req.url).query == 'format=txt':\n            route.fulfill(status=200, headers=headers, content_type='text/plain; charset=utf-8', body='合成修订稿，不是法律结论。'); return\n        data=review")
edit(p, "        with page.expect_download() as download:page.get_by_role('button',name='导出审查报告',exact=True).click()", '''        export_count = sum(path == '/legal/reviews/r1/export' for _, path in calls)
        page.get_by_role('button',name='导出文字修改稿',exact=True).click()
        expect(page.get_by_role('dialog', name='导出前，检查文件中的敏感信息')).to_be_visible()
        assert sum(path == '/legal/reviews/r1/export' for _, path in calls) == export_count
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        page.get_by_role('button',name='导出文字修改稿',exact=True).click()
        with page.expect_download() as revision:
            page.get_by_role('button',name='确认并导出修订稿',exact=True).click()
        revision.value.save_as(OUT/'synthetic-revision.txt')
        with page.expect_download() as download:page.get_by_role('button',name='导出审查报告',exact=True).click()''')
edit(p, '        assert not errors,errors', "        assert not errors,errors\n        assert not AXE_VIOLATIONS, AXE_VIOLATIONS")
print('Applied browser-audit corrections and explicit sensitive-export dialog')

p='frontend/src/legal/DeskExperience.tsx'
edit(p, '  const ref = useRef<HTMLDialogElement>(null);', '  const ref = useRef<HTMLDialogElement>(null);\n  const cancelRef = useRef<HTMLButtonElement>(null);')
edit(p, '    dialog?.showModal();\n    return () => { dialog?.close(); if (previous?.isConnected) previous.focus(); };', '''    dialog?.showModal();
    // React autofocus runs while the native dialog is still closed. Focus after showModal.
    cancelRef.current?.focus();
    const frame = requestAnimationFrame(() => cancelRef.current?.focus());
    return () => { cancelAnimationFrame(frame); dialog?.close(); if (previous?.isConnected) previous.focus(); };''')
edit(p, 'aria-labelledby="lv-dialog-title"\n    onCancel=', '''aria-labelledby="lv-dialog-title"
    onKeyDown={event => {
      if (event.key !== 'Tab') return;
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'));
      if (!items.length) { event.preventDefault(); return; }
      const index = items.indexOf(document.activeElement as HTMLElement);
      if ((event.shiftKey && index <= 0) || (!event.shiftKey && (index === items.length - 1 || index < 0))) {
        event.preventDefault(); items[event.shiftKey ? items.length - 1 : 0].focus();
      }
    }}
    onCancel=''')
edit(p, '<button type="button" className="lv-secondary" disabled={busy} onClick={onCancel} autoFocus>', '<button ref={cancelRef} type="button" className="lv-secondary" disabled={busy} onClick={onCancel}>')
css=Path('frontend/src/legal/LegalDesk.css')
s=css.read_text()
for color in ['#65738c','#657590','#657690','#67778e','#68778c','#69748a','#69758b','#6a7587','#6a7890','#6a7d9b','#6b778b','#6b7b96','#6c7688','#6c7d98','#7382a0','#747e8f','#75829a','#788293']:
    s=s.replace(color, '#586880')
css.write_text(s)
p='frontend/src/legal/LegalDesk.tsx'
edit(p, "format === 'md' ? '合同审查报告' : '合同修订稿（含修订痕迹）'", "format === 'md' ? '合同审查报告' : format === 'docx' ? '合同修订稿（含修订痕迹）' : '合同文字修改稿'")
edit(p, "'修订稿已导出，请在 Word「审阅」中逐项确认。'", "format === 'docx' ? '修订稿已导出，请在 Word「审阅」中逐项确认。' : '文字修改稿已导出，请对照原合同复核，不包含 Word 修订标记。'")
p='scripts/legal_ui_smoke.py'
edit(p, 'from contextlib import contextmanager', 'import traceback\nfrom contextlib import contextmanager')
edit(p, "            page.screenshot(path=str(OUT/'failure.png'), full_page=True)", "            (OUT/'failure.txt').write_text(traceback.format_exc() + '\\nACTIVE: ' + str(page.evaluate('document.activeElement.outerHTML')), encoding='utf-8')\n            page.screenshot(path=str(OUT/'failure.png'), full_page=True)")
print('Applied explicit modal focus, keyboard containment and legible muted text')
