/* Shared dismissal for static dialogs, dynamic previews and reading panels. */
'use strict';
(() => {
  const sessions = new WeakMap();
  const guarded = new Set(['project-dialog', 'model-dialog', 'preflight-dialog']);

  function values(dialog) {
    return JSON.stringify([...dialog.querySelectorAll('input, textarea, select')]
      .filter(input => !input.disabled && !['button', 'submit', 'hidden', 'search'].includes(input.type))
      .map(input => [input.id || input.name, input.type,
        ['checkbox', 'radio'].includes(input.type) ? input.checked
          : input.multiple ? [...input.selectedOptions].map(option => option.value) : input.value]));
  }

  function requestClose(dialog) {
    if (!dialog.open) return;
    // The existing cancel handlers retain control over unsaved edits and workflow cleanup.
    const event = new Event('cancel', {cancelable: true});
    if (dialog.dispatchEvent(event) && dialog.open) dialog.close();
  }

  function prepare(dialog) {
    let session = sessions.get(dialog);
    if (!session) {
      session = {open: false, baseline: ''}; sessions.set(dialog, session);
      dialog.addEventListener('cancel', event => {
        if (event.defaultPrevented) return;
        if (guarded.has(dialog.id) && values(dialog) !== session.baseline
            && !confirm('当前窗口有尚未保存的修改，确定退出吗？')) {
          event.preventDefault(); return;
        }
        const route = {'review-dialog': 'return-facts', 'preflight-dialog': 'preflight-cancel'}[dialog.id];
        if (route) {
          const control = document.getElementById(route);
          if (control) { event.preventDefault(); control.click(); }
        }
      });
      dialog.addEventListener('close', () => { if (!dialog.open) session.open = false; });
    }
    dialog.classList.add('has-dialog-dismiss');
    if (!dialog.querySelector('.dialog-dismiss-button')) {
      const close = document.createElement('button');
      close.type = 'button'; close.className = 'secondary dialog-dismiss-button';
      close.setAttribute('aria-label', '关闭窗口'); close.title = '关闭窗口';
      const glyph = document.createElement('span'); glyph.textContent = '×';
      glyph.setAttribute('aria-hidden', 'true'); close.append(glyph);
      close.addEventListener('click', () => requestClose(dialog));
      const header = dialog.querySelector(':scope > .studio-dialog-bar, :scope > .experience-command-head, :scope > .design-picker-heading');
      if (header) {
        header.classList.add('dialog-dismiss-header');
        for (const button of header.querySelectorAll('button')) {
          if (/^关闭(?:窗口)?$/.test(button.textContent.trim())) button.classList.add('dialog-dismiss-original');
        }
        header.append(close);
      } else {
        // No content or forms are moved, so existing selectors and submit handlers keep working.
        let rail = dialog.querySelector(':scope > .dialog-dismiss-rail');
        if (!rail) {
          rail = document.createElement('div'); rail.className = 'dialog-dismiss-rail';
          dialog.prepend(rail);
        }
        rail.append(close);
        const title = dialog.querySelector('h1, h2, h3');
        if (title) title.classList.add('dialog-dismiss-title');
      }
    }
    if (dialog.open && !session.open) {
      session.baseline = values(dialog); session.open = true;
    } else if (!dialog.open) session.open = false;
  }

  const scan = () => document.querySelectorAll('dialog').forEach(prepare);
  scan();
  new MutationObserver(mutations => {
    // A close followed immediately by reopening is a new editing session too.
    for (const change of mutations) {
      if (change.type === 'attributes' && change.oldValue === null) {
        const session = sessions.get(change.target);
        if (session) session.open = false;
      }
    }
    scan();
  }).observe(document.body, {subtree: true, childList: true, attributes: true,
    attributeOldValue: true, attributeFilter: ['open']});
})();
