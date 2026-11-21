const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

$$('[data-tab]').forEach(button => button.addEventListener('click', () => {
  $$('[data-tab],.tab').forEach(element => element.classList.remove('active'));
  button.classList.add('active');
  document.getElementById(button.dataset.tab).classList.add('active');
}));
$$('[data-dialog]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.dialog).showModal()));
$$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$$('[data-confirm]').forEach(form => form.addEventListener('submit', event => {
  if (!confirm(form.dataset.confirm)) event.preventDefault();
}));
const videoDialog = $('#video-dialog');
if (videoDialog) {
  const video = $('video', videoDialog);
  const stopPreview = () => {
    video.pause();
    video.removeAttribute('src');
    video.load();
  };
  $$('[data-video]').forEach(button => button.addEventListener('click', event => {
    event.stopPropagation();
    stopPreview();
    video.src = button.dataset.video;
    videoDialog.showModal();
  }));
  videoDialog.addEventListener('close', stopPreview);
  videoDialog.addEventListener('click', event => {
    const bounds = videoDialog.getBoundingClientRect();
    const outside = event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
    if (outside) videoDialog.close();
  });
  window.addEventListener('pagehide', stopPreview);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) return;
    if (videoDialog.open) videoDialog.close(); else stopPreview();
  });
}

const upload = $('#upload-input'), uploadForm = $('#upload-form'), drop = $('#drop-zone');
if (upload) upload.addEventListener('change', () => uploadForm.requestSubmit());
if (drop) {
  ['dragenter', 'dragover'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.remove('drag'); }));
  drop.addEventListener('drop', event => { upload.files = event.dataTransfer.files; uploadForm.requestSubmit(); });
}
const recurrence = $('#recurrence'), rrule = $('#rrule');
if (recurrence) recurrence.addEventListener('change', () => { if (recurrence.value !== 'custom') rrule.value = recurrence.value; });

const explorer = $('[data-explorer]');
if (explorer) {
  const items = $$('.explorer-item', explorer), selected = new Set();
  const count = $('[data-selection-count]'), menu = $('#item-context-menu'), sort = $('[data-sort]');
  let anchor = null, menuItem = null, longPress = null;
  const formatBytes = value => {
    const bytes = Number(value); if (!bytes) return '—';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
  };
  $$('.detail-size[data-bytes]', explorer).forEach(element => { element.textContent = formatBytes(element.dataset.bytes); });
  $$('.detail-modified', explorer).forEach(element => { element.textContent = new Date(element.dateTime).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }); });
  const updateSelection = () => {
    items.forEach(item => {
      const active = selected.has(item.dataset.path);
      item.classList.toggle('selected', active); item.setAttribute('aria-selected', String(active));
    });
    count.textContent = `${selected.size} selected`;
    $$('[data-bulk-action]').forEach(button => { button.disabled = !selected.size; });
  };
  const selectOnly = item => { selected.clear(); selected.add(item.dataset.path); anchor = item; updateSelection(); };
  const toggle = item => { selected.has(item.dataset.path) ? selected.delete(item.dataset.path) : selected.add(item.dataset.path); anchor = item; updateSelection(); };
  const range = item => {
    if (!anchor) return selectOnly(item);
    const start = items.indexOf(anchor), end = items.indexOf(item);
    items.slice(Math.min(start, end), Math.max(start, end) + 1).forEach(row => selected.add(row.dataset.path)); updateSelection();
  };
  const paths = () => [...selected];
  const fillPaths = form => {
    const container = $('[data-path-fields]', form);
    container.replaceChildren(...paths().map(path => { const input = document.createElement('input'); input.type = 'hidden'; input.name = 'paths'; input.value = path; return input; }));
  };
  const openBulk = action => {
    if (!selected.size) return;
    if (action === 'trash') { const form = $('#bulk-trash-form'); fillPaths(form); form.requestSubmit(); return; }
    const dialog = document.getElementById(`${action}-dialog`); fillPaths($('form', dialog)); dialog.showModal();
  };
  const openItem = item => {
    if (item.dataset.kind === 'folder') location.href = `/?path=${encodeURIComponent(item.dataset.path)}`;
    else item.querySelector('[data-video]')?.click();
  };
  const rename = item => {
    const dialog = $('#rename-dialog'), form = $('form', dialog);
    form.elements.source.value = item.dataset.path; form.elements.name.value = item.dataset.name;
    dialog.showModal(); form.elements.name.select();
  };
  const closeMenu = () => { menu.hidden = true; menuItem = null; };
  const showMenu = (item, x, y) => {
    if (!selected.has(item.dataset.path)) selectOnly(item);
    menuItem = item; menu.hidden = false;
    $('[data-context-action="preview"]', menu).hidden = item.dataset.kind !== 'video';
    const width = menu.offsetWidth, height = menu.offsetHeight;
    menu.style.left = `${Math.min(x, innerWidth - width - 8)}px`; menu.style.top = `${Math.min(y, innerHeight - height - 8)}px`;
    $('[data-context-action="open"]', menu).focus();
  };
  items.forEach(item => {
    item.addEventListener('click', event => {
      if (event.target.closest('button,a')) return;
      if (event.shiftKey) range(item); else if (event.ctrlKey || event.metaKey) toggle(item); else selectOnly(item);
    });
    item.addEventListener('dblclick', event => { if (!event.target.closest('.item-menu')) openItem(item); });
    item.addEventListener('contextmenu', event => { event.preventDefault(); showMenu(item, event.clientX, event.clientY); });
    item.addEventListener('pointerdown', event => { if (event.pointerType === 'touch') longPress = setTimeout(() => showMenu(item, event.clientX, event.clientY), 550); });
    ['pointerup', 'pointercancel', 'pointermove'].forEach(name => item.addEventListener(name, () => clearTimeout(longPress)));
    $('[data-item-menu]', item).addEventListener('click', event => { event.stopPropagation(); const rect = event.currentTarget.getBoundingClientRect(); showMenu(item, rect.right, rect.bottom); });
  });
  explorer.addEventListener('click', event => { if (event.target === explorer) { selected.clear(); updateSelection(); } });
  document.addEventListener('click', event => { if (!event.target.closest('#item-context-menu,[data-item-menu]')) closeMenu(); });
  window.addEventListener('blur', closeMenu);
  menu.addEventListener('click', async event => {
    const action = event.target.closest('[data-context-action]')?.dataset.contextAction;
    if (!action || !menuItem) return;
    const item = menuItem; closeMenu();
    if (action === 'open' || action === 'preview') openItem(item);
    else if (action === 'rename') rename(item);
    else if (action === 'copy') await navigator.clipboard.writeText(`${explorer.dataset.plexPrefix.replace(/\/$/, '')}/${item.dataset.path}`);
    else openBulk(action);
  });
  $$('[data-bulk-action]').forEach(button => button.addEventListener('click', () => openBulk(button.dataset.bulkAction)));
  const applySort = value => {
    const [field, direction] = value.split('-'), multiplier = direction === 'desc' ? -1 : 1;
    [...items].sort((a, b) => {
      if ((a.dataset.kind === 'folder') !== (b.dataset.kind === 'folder')) return a.dataset.kind === 'folder' ? -1 : 1;
      if (field === 'size') return (Number(a.dataset.size) - Number(b.dataset.size)) * multiplier;
      if (field === 'modified') return (Date.parse(a.dataset.modified) - Date.parse(b.dataset.modified)) * multiplier;
      const av = field === 'type' ? a.dataset.kind : a.dataset.name, bv = field === 'type' ? b.dataset.kind : b.dataset.name;
      return av.localeCompare(bv, undefined, { numeric: true, sensitivity: 'base' }) * multiplier;
    }).forEach(item => explorer.append(item));
    localStorage.setItem('pga-sort', value);
  };
  sort.value = localStorage.getItem('pga-sort') || 'name-asc'; sort.addEventListener('change', () => applySort(sort.value)); applySort(sort.value);
  const setView = view => {
    explorer.dataset.view = view;
    $$('[data-view]').forEach(button => { const active = button.dataset.view === view; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
    localStorage.setItem('pga-view', view);
  };
  $$('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  setView(localStorage.getItem('pga-view') || 'large');
  document.addEventListener('keydown', event => {
    if (event.target.matches('input,textarea,select') || event.target.closest('dialog[open]')) return;
    const focused = document.activeElement.closest?.('.explorer-item');
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') { event.preventDefault(); items.forEach(item => selected.add(item.dataset.path)); updateSelection(); }
    else if (event.key === 'Delete' && selected.size) { event.preventDefault(); openBulk('trash'); }
    else if (event.key === 'F2' && (focused || selected.size === 1)) { event.preventDefault(); rename(focused || items.find(item => selected.has(item.dataset.path))); }
    else if (event.key === 'Enter' && focused) { event.preventDefault(); openItem(focused); }
    else if (event.key === 'Escape') { selected.clear(); updateSelection(); closeMenu(); }
    else if ((event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) && focused) { event.preventDefault(); const rect = focused.getBoundingClientRect(); showMenu(focused, rect.left + 30, rect.top + 30); }
  });
  const breadcrumbs = $('[data-breadcrumbs]'), parts = (breadcrumbs.dataset.path || '').split('/').filter(Boolean);
  const root = document.createElement('a'); root.href = '/'; root.textContent = 'Pre-rolls'; breadcrumbs.append(root);
  parts.forEach((part, index) => { const separator = document.createElement('span'); separator.textContent = '›'; breadcrumbs.append(separator); const link = document.createElement('a'); link.textContent = part; link.href = `/?path=${encodeURIComponent(parts.slice(0, index + 1).join('/'))}`; breadcrumbs.append(link); });
  updateSelection();
}

const calendarGrid = $('[data-calendar-grid]');
if (calendarGrid) {
  let shown = new Date();
  const render = async () => {
    const events = await fetch('/api/calendar').then(response => response.json()), year = shown.getFullYear(), month = shown.getMonth();
    const first = new Date(year, month, 1), last = new Date(year, month + 1, 0);
    $('[data-calendar-title]').textContent = first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }); calendarGrid.innerHTML = '';
    ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(day => calendarGrid.insertAdjacentHTML('beforeend', `<b>${day}</b>`));
    for (let index = 0; index < first.getDay(); index += 1) calendarGrid.insertAdjacentHTML('beforeend', '<div></div>');
    for (let day = 1; day <= last.getDate(); day += 1) {
      const date = new Date(year, month, day), cell = document.createElement('div'); cell.innerHTML = `<span>${day}</span>`;
      events.forEach(event => { const start = new Date(event.starts_at), annual = (event.rrule || '').includes('YEARLY'); const same = annual ? start.getMonth() === month && start.getDate() === day : start.toDateString() === date.toDateString(); if (same) cell.insertAdjacentHTML('beforeend', `<small style="--event:${event.color}">${event.name}</small>`); });
      calendarGrid.appendChild(cell);
    }
  };
  $('[data-calendar-prev]').onclick = () => { shown = new Date(shown.getFullYear(), shown.getMonth() - 1, 1); render(); };
  $('[data-calendar-next]').onclick = () => { shown = new Date(shown.getFullYear(), shown.getMonth() + 1, 1); render(); };
  render();
}
