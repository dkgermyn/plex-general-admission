const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const activateTab = name => {
  $$('[data-tab],.tab').forEach(element => element.classList.remove('active'));
  const button = $(`[data-tab="${name}"]`);
  if (!button || !document.getElementById(name)) return;
  button.classList.add('active');
  document.getElementById(name).classList.add('active');
};
$$('[data-tab]').forEach(button => button.addEventListener('click', () => {
  activateTab(button.dataset.tab);
  const url = new URL(location.href); url.searchParams.set('tab', button.dataset.tab); history.replaceState({}, '', url);
}));
activateTab(new URLSearchParams(location.search).get('tab') || 'library');
$$('[data-dialog]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.dialog).showModal()));
$$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
const confirmDialog = $('#confirm-dialog');
let pendingConfirmation = null;
$$('[data-confirm]').forEach(form => form.addEventListener('submit', event => {
  if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
  event.preventDefault();
  pendingConfirmation = form;
  $('[data-confirm-message]', confirmDialog).textContent = form.dataset.confirm;
  confirmDialog.showModal();
}));
$('[data-confirm-accept]', confirmDialog)?.addEventListener('click', () => {
  if (!pendingConfirmation) return;
  const form = pendingConfirmation;
  pendingConfirmation = null;
  confirmDialog.close();
  form.dataset.confirmed = 'true';
  form.requestSubmit();
});
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
const conflictDialog = $('#conflict-dialog');
const showConflicts = (conflicts, message, uploadChoices = false) => {
  $('[data-conflict-message]', conflictDialog).textContent = message;
  $('[data-conflict-list]', conflictDialog).replaceChildren(...conflicts.map(name => { const item = document.createElement('li'); item.textContent = name; return item; }));
  $('[data-upload-conflict-actions]', conflictDialog).hidden = !uploadChoices;
  conflictDialog.showModal();
};
let pendingUpload = [];
const submitUpload = (files, conflict = 'error') => {
  if (!files.length) return;
  pendingUpload = [...files];
  const data = new FormData(uploadForm);
  data.delete('upload'); data.set('conflict', conflict);
  pendingUpload.forEach(file => data.append('upload', file, file.name));
  const status = $('[data-upload-status]'), progress = $('progress', status);
  status.hidden = false; progress.value = 0;
  $('[data-upload-label]', status).textContent = `Uploading ${pendingUpload.length} file${pendingUpload.length === 1 ? '' : 's'}…`;
  $('[data-upload-detail]', status).textContent = pendingUpload.map(file => file.name).join(', ');
  const request = new XMLHttpRequest();
  request.open('POST', uploadForm.action); request.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
  request.upload.addEventListener('progress', event => {
    const percent = event.lengthComputable ? Math.round(event.loaded / event.total * 100) : 0;
    progress.value = percent; $('[data-upload-percent]', status).textContent = `${percent}%`;
  });
  request.addEventListener('load', () => {
    let result = {}; try { result = JSON.parse(request.responseText); } catch (_) { /* response is not JSON */ }
    if (request.status === 409) {
      status.hidden = true;
      showConflicts(result.conflicts || [], 'These files already exist in this folder.', true);
      return;
    }
    if (request.status < 200 || request.status >= 300) {
      $('[data-upload-label]', status).textContent = 'Upload failed';
      $('[data-upload-detail]', status).textContent = result.detail || `Server returned ${request.status}`;
      return;
    }
    progress.value = 100; $('[data-upload-percent]', status).textContent = '100%';
    $('[data-upload-label]', status).textContent = `${result.uploaded.length} uploaded${result.skipped.length ? `, ${result.skipped.length} skipped` : ''}`;
    setTimeout(() => location.reload(), 700);
  });
  request.addEventListener('error', () => { $('[data-upload-label]', status).textContent = 'Upload failed'; $('[data-upload-detail]', status).textContent = 'The connection was interrupted.'; });
  request.send(data);
};
if (upload) upload.addEventListener('change', () => submitUpload(upload.files));
uploadForm?.addEventListener('submit', event => { event.preventDefault(); submitUpload(upload.files); });
$$('[data-conflict-choice]').forEach(button => button.addEventListener('click', () => { conflictDialog.close(); submitUpload(pendingUpload, button.dataset.conflictChoice); }));
if (drop) {
  ['dragenter', 'dragover'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.remove('drag'); }));
  drop.addEventListener('drop', event => submitUpload(event.dataTransfer.files));
}
const recurrenceLabels = { '': 'Does not repeat.', 'FREQ=DAILY': 'Repeats every day.', 'FREQ=WEEKLY': 'Repeats every week.', 'FREQ=MONTHLY': 'Repeats every month.', 'FREQ=YEARLY': 'Repeats every year.' };
const updateRecurrence = recurrence => {
  const form = recurrence.closest('form'), custom = $('[data-custom-rule]', form), rrule = $('[data-rrule]', form), summary = $('[data-recurrence-summary]', form);
  const isCustom = recurrence.value === 'custom';
  custom.hidden = !isCustom;
  if (!isCustom) { rrule.value = recurrence.value; rrule.setCustomValidity(''); }
  else rrule.setCustomValidity(rrule.value && !/^FREQ=/i.test(rrule.value.trim()) ? 'A custom rule must begin with FREQ=' : '');
  summary.textContent = isCustom ? (rrule.value ? `Custom rule: ${rrule.value}` : 'Enter a custom recurrence rule.') : recurrenceLabels[recurrence.value];
};
$$('[data-recurrence]').forEach(recurrence => {
  recurrence.addEventListener('change', () => updateRecurrence(recurrence));
  $('[data-rrule]', recurrence.closest('form')).addEventListener('input', () => updateRecurrence(recurrence));
  updateRecurrence(recurrence);
});

const colorText = value => {
  const hex = value.replace('#', ''), red = parseInt(hex.slice(0, 2), 16), green = parseInt(hex.slice(2, 4), 16), blue = parseInt(hex.slice(4, 6), 16);
  return 0.299 * red + 0.587 * green + 0.114 * blue > 160 ? '#17120a' : '#ffffff';
};
const updateColor = control => {
  const input = $('input[type="color"]', control), preview = $('[data-color-preview]', control);
  $('[data-color-value]', control).textContent = input.value.toUpperCase();
  preview.style.setProperty('--chosen-color', input.value); preview.style.setProperty('--chosen-text', colorText(input.value));
};
$$('[data-color-control]').forEach(control => { $('input[type="color"]', control).addEventListener('input', () => updateColor(control)); updateColor(control); });

$$('[data-edit-collection]').forEach(button => button.addEventListener('click', () => {
  const dialog = $('#edit-collection-dialog'), form = $('form', dialog);
  form.action = `/collections/${button.dataset.id}/edit`;
  form.elements.name.value = button.dataset.name; form.elements.description.value = button.dataset.description || '';
  form.elements.color.value = button.dataset.color; updateColor($('[data-color-control]', form));
  dialog.showModal();
}));
$$('[data-add-members]').forEach(button => button.addEventListener('click', () => {
  const dialog = $('#add-members-dialog'), form = $('form', dialog);
  form.action = `/collections/${button.dataset.id}/selections`;
  $('[data-collection-name]', dialog).textContent = button.dataset.name;
  $$('input[type="checkbox"]', dialog).forEach(input => { input.checked = false; });
  $('[data-member-search]', dialog).value = '';
  $$('[data-choice-name]', dialog).forEach(choice => { choice.hidden = false; });
  dialog.showModal();
}));
$('[data-member-search]')?.addEventListener('input', event => {
  const query = event.target.value.trim().toLocaleLowerCase();
  $$('[data-choice-name]', $('#add-members-dialog')).forEach(choice => { choice.hidden = !choice.dataset.choiceName.includes(query); });
});
const openScheduleEditor = schedule => {
  const dialog = $('#edit-schedule-dialog'), form = $('form', dialog);
  form.action = `/schedules/${schedule.id}/edit`;
  ['name', 'collection_id', 'starts_at', 'ends_at', 'rrule', 'color', 'priority', 'overlap_policy'].forEach(name => { if (form.elements[name]) form.elements[name].value = schedule[name] ?? ''; });
  const recurrence = $('[data-recurrence]', form), presets = ['', 'FREQ=DAILY', 'FREQ=WEEKLY', 'FREQ=MONTHLY', 'FREQ=YEARLY'];
  recurrence.value = presets.includes(schedule.rrule || '') ? (schedule.rrule || '') : 'custom';
  updateRecurrence(recurrence); updateColor($('[data-color-control]', form));
  dialog.showModal();
};
$$('[data-edit-schedule]').forEach(button => button.addEventListener('click', () => openScheduleEditor(JSON.parse(button.dataset.schedule))));

const inspector = $('[data-play-inspector]');
if (inspector) {
  const form = $('[data-inspector-form]', inspector), at = form.elements.at;
  const renderInspection = result => {
    $('[data-inspector-explanation]', inspector).textContent = result.explanation;
    $('[data-inspector-count]', inspector).textContent = `${result.paths.length} eligible video${result.paths.length === 1 ? '' : 's'}`;
    const schedules = $('[data-inspector-schedules]', inspector); schedules.innerHTML = '';
    result.schedules.forEach(item => { const pill = document.createElement('span'); pill.className = `pill${item.selected ? '' : ' muted-pill'}`; pill.textContent = `${item.name} · P${item.priority} · ${item.reason}`; schedules.appendChild(pill); });
    const warning = $('[data-inspector-empty]', inspector); warning.hidden = result.empty_collections.length === 0;
    $('span', warning).textContent = result.empty_collections.join(', ');
  };
  const inspect = async value => renderInspection(await fetch(`/api/inspect${value ? `?at=${encodeURIComponent(value)}` : ''}`).then(response => response.json()));
  form.addEventListener('submit', event => { event.preventDefault(); inspect(at.value); });
  $('[data-inspect-now]', inspector).addEventListener('click', () => { at.value = ''; inspect(''); });
}

const zoneSelect = $('[data-timezone-select]'), zoneClock = $('[data-zone-clock]');
const updateZonePreview = () => {
  if (!zoneSelect) return;
  const zone = zoneSelect.value;
  $('[data-timezone-preview]').textContent = `December 1, 2026 at 12:00 AM in ${zone}`;
};
if (zoneSelect) { zoneSelect.addEventListener('change', updateZonePreview); updateZonePreview(); }
if (zoneClock) {
  const tick = () => { zoneClock.textContent = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZone: zoneClock.dataset.timezone, timeZoneName: 'short' }).format(new Date()); };
  tick(); setInterval(tick, 1000);
}

const explorer = $('[data-explorer]');
if (explorer) {
  const items = $$('.explorer-item', explorer), selected = new Set();
  const count = $('[data-selection-count]'), menu = $('#item-context-menu'), sort = $('[data-sort]');
  const search = $('[data-library-search]'), filter = $('[data-filter]'), collectionFilter = $('[data-collection-filter]'), currentPath = explorer.dataset.currentPath || '/';
  const coarsePointer = matchMedia('(pointer: coarse)').matches;
  let anchor = null, menuItem = null, longPress = null, selectionMode = false, suppressClick = false;
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
    explorer.classList.toggle('selection-mode', selectionMode);
    $('[data-select-mode]').textContent = selectionMode ? 'Cancel selection' : 'Select';
  };
  const enterSelection = item => { selectionMode = true; if (item) selected.add(item.dataset.path); anchor = item || anchor; updateSelection(); };
  const exitSelection = () => { selectionMode = false; selected.clear(); anchor = null; updateSelection(); };
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
    $('[data-context-action="open"]', menu).hidden = item.dataset.kind !== 'folder';
    $('[data-context-action="preview"]', menu).hidden = item.dataset.kind !== 'video';
    const width = menu.offsetWidth, height = menu.offsetHeight;
    menu.style.left = `${Math.min(x, innerWidth - width - 8)}px`; menu.style.top = `${Math.min(y, innerHeight - height - 8)}px`;
    $('[data-context-action]:not([hidden])', menu).focus();
  };
  items.forEach(item => {
    item.addEventListener('click', event => {
      if (suppressClick) { suppressClick = false; event.preventDefault(); event.stopPropagation(); return; }
      if (selectionMode) { event.preventDefault(); event.stopPropagation(); toggle(item); return; }
      if (event.target.closest('button,a')) return;
      if (coarsePointer) { openItem(item); return; }
      if (event.shiftKey) range(item); else if (event.ctrlKey || event.metaKey) toggle(item); else selectOnly(item);
    }, true);
    item.addEventListener('dblclick', event => { if (!event.target.closest('.item-menu')) openItem(item); });
    item.addEventListener('contextmenu', event => { event.preventDefault(); showMenu(item, event.clientX, event.clientY); });
    item.addEventListener('pointerdown', event => { if (event.pointerType === 'touch') longPress = setTimeout(() => { suppressClick = true; enterSelection(item); }, 550); });
    ['pointerup', 'pointercancel', 'pointermove'].forEach(name => item.addEventListener(name, () => clearTimeout(longPress)));
    $('[data-item-menu]', item).addEventListener('click', event => { event.stopPropagation(); const rect = event.currentTarget.getBoundingClientRect(); showMenu(item, rect.right, rect.bottom); });
    item.addEventListener('dragstart', event => {
      if (!selected.has(item.dataset.path)) selectOnly(item);
      event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', paths().join('\n'));
    });
    if (item.dataset.kind === 'folder') {
      item.addEventListener('dragover', event => { if (!selected.has(item.dataset.path)) { event.preventDefault(); item.classList.add('drop-target'); } });
      item.addEventListener('dragleave', () => item.classList.remove('drop-target'));
      item.addEventListener('drop', event => { event.preventDefault(); item.classList.remove('drop-target'); moveSelected(item.dataset.path); });
    }
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
  $('[data-select-mode]').addEventListener('click', () => selectionMode ? exitSelection() : enterSelection());
  $('[data-selection-done]').addEventListener('click', exitSelection);
  $('[data-select-all]').addEventListener('click', () => { enterSelection(); selected.clear(); items.filter(item => !item.hidden).forEach(item => selected.add(item.dataset.path)); updateSelection(); });
  const preferenceKey = name => `pga-${name}:${currentPath}`;
  const applySort = value => {
    const [field, direction] = value.split('-'), multiplier = direction === 'desc' ? -1 : 1;
    [...items].sort((a, b) => {
      if ((a.dataset.kind === 'folder') !== (b.dataset.kind === 'folder')) return a.dataset.kind === 'folder' ? -1 : 1;
      if (field === 'size') return (Number(a.dataset.size) - Number(b.dataset.size)) * multiplier;
      if (field === 'modified') return (Date.parse(a.dataset.modified) - Date.parse(b.dataset.modified)) * multiplier;
      const av = field === 'type' ? a.dataset.kind : a.dataset.name, bv = field === 'type' ? b.dataset.kind : b.dataset.name;
      return av.localeCompare(bv, undefined, { numeric: true, sensitivity: 'base' }) * multiplier;
    }).forEach(item => explorer.append(item));
    localStorage.setItem(preferenceKey('sort'), value);
  };
  sort.value = localStorage.getItem(preferenceKey('sort')) || 'name-asc'; sort.addEventListener('change', () => applySort(sort.value)); applySort(sort.value);
  const setView = view => {
    explorer.dataset.view = view;
    $$('[data-view]').forEach(button => { const active = button.dataset.view === view; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
    localStorage.setItem(preferenceKey('view'), view);
  };
  $$('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  setView(localStorage.getItem(preferenceKey('view')) || 'large');
  const applyFilter = () => {
    const query = search.value.trim().toLocaleLowerCase(), kind = filter.value, collection = collectionFilter.value;
    let visible = 0;
    items.forEach(item => {
      const memberships = (item.dataset.collections || '').split('|').filter(Boolean);
      const collectionMatch = collection === 'all' || (collection === 'unassigned' ? item.dataset.kind === 'video' && !memberships.length : memberships.includes(collection));
      const match = (!query || item.dataset.name.toLocaleLowerCase().includes(query)) && (kind === 'all' || item.dataset.kind === kind) && collectionMatch;
      item.hidden = !match; if (match) visible += 1;
    });
    $('[data-filter-count]').textContent = query || kind !== 'all' || collection !== 'all' ? `${visible} of ${items.length}` : `${items.length} items`;
  };
  search.addEventListener('input', applyFilter); filter.addEventListener('change', applyFilter); collectionFilter.addEventListener('change', applyFilter); applyFilter();
  async function moveSelected(destination) {
    if (!selected.size) return;
    const form = $('#move-dialog form'); fillPaths(form); form.elements.destination.value = destination;
    const data = new FormData(form);
    const response = await fetch(form.action, { method: 'POST', body: data, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (response.status === 409) { const result = await response.json(); showConflicts(result.conflicts || [], result.detail || 'Those names already exist.'); return; }
    if (!response.ok) { const result = await response.json().catch(() => ({})); showConflicts([], result.detail || 'The items could not be moved.'); return; }
    location.reload();
  }
  const handleConflictForm = form => form.addEventListener('submit', async event => {
    event.preventDefault();
    if (form.id !== 'rename-form') fillPaths(form);
    const response = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (response.status === 409) { const result = await response.json(); showConflicts(result.conflicts || [], result.detail || 'That name already exists.'); return; }
    if (!response.ok) { const result = await response.json().catch(() => ({})); showConflicts([], result.detail || 'The operation could not be completed.'); return; }
    location.reload();
  });
  handleConflictForm($('#move-dialog form')); handleConflictForm($('#rename-dialog form'));
  document.addEventListener('keydown', event => {
    if (event.target.matches('input,textarea,select') || event.target.closest('dialog[open]')) return;
    const focused = document.activeElement.closest?.('.explorer-item');
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') { event.preventDefault(); items.forEach(item => selected.add(item.dataset.path)); updateSelection(); }
    else if (event.key === 'Delete' && selected.size) { event.preventDefault(); openBulk('trash'); }
    else if (event.key === 'F2' && (focused || selected.size === 1)) { event.preventDefault(); rename(focused || items.find(item => selected.has(item.dataset.path))); }
    else if (event.key === 'Enter' && focused) { event.preventDefault(); openItem(focused); }
    else if (event.key === 'Escape') { exitSelection(); closeMenu(); }
    else if ((event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) && focused) { event.preventDefault(); const rect = focused.getBoundingClientRect(); showMenu(focused, rect.left + 30, rect.top + 30); }
  });
  const breadcrumbs = $('[data-breadcrumbs]'), parts = (breadcrumbs.dataset.path || '').split('/').filter(Boolean);
  const root = document.createElement('a'); root.href = '/'; root.textContent = 'Pre-rolls'; breadcrumbs.append(root);
  parts.forEach((part, index) => { const separator = document.createElement('span'); separator.textContent = '›'; breadcrumbs.append(separator); const link = document.createElement('a'); link.textContent = part; link.href = `/?path=${encodeURIComponent(parts.slice(0, index + 1).join('/'))}`; breadcrumbs.append(link); });
  updateSelection();
}

const calendarGrid = $('[data-calendar-grid]');
if (calendarGrid) {
  let shown = new Date(), selectionStart = null, resizing = null, resizeTarget = null;
  const pad = value => String(value).padStart(2, '0');
  const dateValue = date => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const dateTimeValue = date => `${dateValue(date)}T00:00`;
  const dateFromValue = value => { const [year, month, day] = value.split('-').map(Number); return new Date(year, month - 1, day); };
  const highlightSelection = end => {
    if (!selectionStart) return;
    const low = selectionStart < end ? selectionStart : end, high = selectionStart < end ? end : selectionStart;
    $$('[data-calendar-date]', calendarGrid).forEach(cell => cell.classList.toggle('selecting', cell.dataset.calendarDate >= low && cell.dataset.calendarDate <= high));
  };
  const createFromSelection = end => {
    const low = selectionStart < end ? selectionStart : end, high = selectionStart < end ? end : selectionStart;
    const start = dateFromValue(low), finish = dateFromValue(high); finish.setDate(finish.getDate() + 1);
    const form = $('[data-new-schedule]'); form.elements.starts_at.value = dateTimeValue(start); form.elements.ends_at.value = dateTimeValue(finish);
    $('[data-calendar-selection]').textContent = `Selected ${low} through ${high}; the end is exclusive.`;
    form.scrollIntoView({ behavior: 'smooth', block: 'start' }); form.elements.name.focus();
    selectionStart = null; $$('[data-calendar-date]', calendarGrid).forEach(cell => cell.classList.remove('selecting'));
  };
  const resizeTo = async date => {
    const schedule = resizing.schedule, chosen = dateFromValue(date), start = schedule.starts_at.slice(0, 16), end = schedule.ends_at.slice(0, 16);
    let nextStart = start, nextEnd = end;
    if (resizing.edge === 'start') nextStart = `${dateValue(chosen)}T${start.slice(11)}`;
    else { chosen.setDate(chosen.getDate() + 1); nextEnd = `${dateValue(chosen)}T${end.slice(11)}`; }
    const data = new FormData(); data.set('csrf_token', $('[data-new-schedule] [name="csrf_token"]').value); data.set('starts_at', nextStart); data.set('ends_at', nextEnd);
    const response = await fetch(`/schedules/${schedule.id}/bounds`, { method: 'POST', body: data });
    resizing = null;
    if (!response.ok) { alert((await response.json()).detail || 'Could not resize schedule'); return; }
    await render();
  };
  document.addEventListener('pointermove', event => {
    if (!resizing) return;
    const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-calendar-date]');
    if (cell) resizeTarget = cell.dataset.calendarDate;
  });
  document.addEventListener('pointerup', () => { if (resizing && resizeTarget) resizeTo(resizeTarget); });
  const render = async () => {
    const year = shown.getFullYear(), month = shown.getMonth();
    const result = await fetch(`/api/calendar?year=${year}&month=${month + 1}`).then(response => response.json()), events = result.events;
    const first = new Date(year, month, 1), last = new Date(year, month + 1, 0);
    $('[data-calendar-title]').textContent = first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }); calendarGrid.innerHTML = '';
    ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(day => calendarGrid.insertAdjacentHTML('beforeend', `<b>${day}</b>`));
    for (let index = 0; index < first.getDay(); index += 1) calendarGrid.insertAdjacentHTML('beforeend', '<div></div>');
    $('[data-calendar-zone]').textContent = result.timezone;
    for (let day = 1; day <= last.getDate(); day += 1) {
      const cell = document.createElement('div'), number = document.createElement('span'), date = new Date(year, month, day); number.textContent = day; cell.appendChild(number); cell.dataset.calendarDate = dateValue(date);
      const status = result.day_status[String(day)]; if (status?.conflict) cell.classList.add('has-conflict'); if (status?.exclusive_cutoff !== null) cell.classList.add('has-exclusive');
      cell.addEventListener('pointerdown', event => { if (event.target.closest('.calendar-event')) return; selectionStart = cell.dataset.calendarDate; highlightSelection(selectionStart); });
      cell.addEventListener('pointerenter', () => { if (resizing) resizeTarget = cell.dataset.calendarDate; else highlightSelection(cell.dataset.calendarDate); });
      cell.addEventListener('pointerup', () => { if (!resizing && selectionStart) createFromSelection(cell.dataset.calendarDate); });
      events.forEach(schedule => { if (!schedule.days.includes(day)) return; const label = document.createElement('button'); label.type = 'button'; label.className = 'calendar-event'; label.style.setProperty('--event', schedule.color); label.title = `${schedule.name} · ${schedule.collection_name} · Priority ${schedule.priority} · ${schedule.overlap_policy}`; label.textContent = schedule.name; label.addEventListener('click', event => { if (!event.target.closest('.event-handle')) openScheduleEditor(schedule); });
        if (!schedule.rrule && day === schedule.start_day) { const handle = document.createElement('span'); handle.className = 'event-handle start'; handle.title = 'Drag start'; handle.textContent = '↤'; handle.addEventListener('pointerdown', event => { event.stopPropagation(); resizing = { schedule, edge: 'start' }; resizeTarget = cell.dataset.calendarDate; }); label.prepend(handle); }
        if (!schedule.rrule && day === schedule.end_day) { const handle = document.createElement('span'); handle.className = 'event-handle end'; handle.title = 'Drag end'; handle.textContent = '↦'; handle.addEventListener('pointerdown', event => { event.stopPropagation(); resizing = { schedule, edge: 'end' }; resizeTarget = cell.dataset.calendarDate; }); label.append(handle); }
        if (!schedule.video_count) label.classList.add('empty-event'); cell.appendChild(label); });
      calendarGrid.appendChild(cell);
    }
  };
  $('[data-calendar-prev]').onclick = () => { shown = new Date(shown.getFullYear(), shown.getMonth() - 1, 1); render(); };
  $('[data-calendar-next]').onclick = () => { shown = new Date(shown.getFullYear(), shown.getMonth() + 1, 1); render(); };
  render();
}
