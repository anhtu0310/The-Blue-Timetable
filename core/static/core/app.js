/* Blue Time Table – small amount of glue: pop-up, calendar, date picker and people picker. */
(function () {
  'use strict';

  function normalize(text) {
    return (text || '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
      .normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  // --- pop-up ---------------------------------------------------------------
  let modal;
  let changedWhileOpen = false;

  function setupModal() {
    modal = document.getElementById('modal');
    document.body.addEventListener('htmx:afterSwap', function (e) {
      if (e.detail.target.id === 'modal-body') {
        if (!modal.open) modal.showModal();
        modal.querySelector('#modal-body').focus();
        modal.scrollTop = 0;
      }
      initWidgets(e.detail.target);
    });
    modal.addEventListener('click', function (e) {
      if (e.target === modal || e.target.closest('[data-close]')) modal.close();
    });
    document.body.addEventListener('calendarChanged', function () { changedWhileOpen = true; });
    modal.addEventListener('close', function () {
      // Pages without a live calendar reload so their tables show the change.
      if (changedWhileOpen && !document.getElementById('calendar')) window.location.reload();
      changedWhileOpen = false;
    });
  }

  // --- mobile menu ---------------------------------------------------------
  function setupMenu() {
    const button = document.querySelector('[data-menu]');
    const sidebar = document.getElementById('sidebar');
    if (!button || !sidebar) return;
    let scrim = null;
    function close() { sidebar.classList.remove('open'); if (scrim) { scrim.remove(); scrim = null; } }
    button.addEventListener('click', function () {
      sidebar.classList.add('open');
      scrim = document.createElement('div');
      scrim.className = 'scrim';
      scrim.addEventListener('click', close);
      document.body.appendChild(scrim);
    });
  }

  // --- calendar -------------------------------------------------------------
  function setupCalendar() {
    const el = document.getElementById('calendar');
    if (!el || !window.FullCalendar) return;
    const onlyMine = document.getElementById('only-mine');
    const stats = document.getElementById('month-stats');
    let statsMonth = null;
    function loadStats() {
      if (!stats || !statsMonth) return;
      const mine = onlyMine && onlyMine.checked ? '1' : '';
      htmx.ajax('GET', stats.dataset.url + '?month=' + statsMonth + '&mine=' + mine, { target: stats });
    }
    const narrow = window.innerWidth < 640;
    const calendar = new FullCalendar.Calendar(el, {
      locale: 'vi',
      firstDay: 1,
      initialView: narrow ? 'listWeek' : 'dayGridMonth',
      headerToolbar: narrow
        ? { left: 'prev,next', center: 'title', right: 'today' }
        : { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,listWeek' },
      height: 'auto',
      dayMaxEvents: 3,
      eventDisplay: 'block',
      displayEventEnd: false,
      buttonText: { today: 'Hôm nay', month: 'Tháng', week: 'Tuần', list: 'Danh sách' },
      eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
      slotMinTime: '07:00:00',
      slotMaxTime: '22:00:00',
      events: {
        url: el.dataset.eventsUrl,
        extraParams: function () { return { mine: onlyMine && onlyMine.checked ? '1' : '' }; },
      },
      eventContent: function (arg) {
        // Two compact lines in month view: "17:30 Toán" / "TO0600 · P.101".
        if (arg.view.type !== 'dayGridMonth') return true;
        const p = arg.event.extendedProps;
        const top = document.createElement('div');
        top.className = 'ev-line';
        top.innerHTML = '<b></b> <span></span>';
        top.children[0].textContent = arg.timeText;
        top.children[1].textContent = p.subject;
        const bottom = document.createElement('div');
        bottom.className = 'ev-sub';
        bottom.textContent = p.code + (p.room ? ' · P.' + p.room : '');
        return { domNodes: [top, bottom] };
      },
      eventDidMount: function (arg) {
        arg.el.title = arg.event.title;
      },
      datesSet: function (info) {
        // The month in the middle of the visible range is the one the statistics describe.
        const mid = new Date((info.start.getTime() + info.end.getTime()) / 2);
        statsMonth = mid.getFullYear() + '-' + String(mid.getMonth() + 1).padStart(2, '0');
        loadStats();
      },
      eventClick: function (info) {
        info.jsEvent.preventDefault();
        htmx.ajax('GET', info.event.extendedProps.url, { target: '#modal-body' });
      },
    });
    calendar.render();
    if (onlyMine) onlyMine.addEventListener('change', function () { calendar.refetchEvents(); loadStats(); });
    document.body.addEventListener('calendarChanged', function () { calendar.refetchEvents(); loadStats(); });
  }

  // --- form widgets ---------------------------------------------------------
  // Date and time pickers always show dd/mm/yyyy and 24-hour time, whatever the browser language.
  function vnLocale() { return (window.flatpickr && flatpickr.l10ns && flatpickr.l10ns.vn) || 'default'; }

  function setupDatePickers(root) {
    if (!window.flatpickr) return;
    root.querySelectorAll('input[data-multidate]').forEach(function (input) {
      if (input._flatpickr) return;
      flatpickr(input, { mode: 'multiple', dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
                         conjunction: ', ', locale: vnLocale() });
    });
    root.querySelectorAll('input[type=date]').forEach(function (input) {
      if (input._flatpickr) return;
      flatpickr(input, { dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y', allowInput: true,
                         locale: vnLocale() });
    });
    root.querySelectorAll('input[type=time]').forEach(function (input) {
      if (input._flatpickr) return;
      flatpickr(input, { enableTime: true, noCalendar: true, dateFormat: 'H:i', time_24hr: true,
                         minuteIncrement: 15, allowInput: true, locale: vnLocale() });
    });
  }

  function setupPicker(picker, subjectSelect) {
    const filter = picker.querySelector('[data-picker-filter]');
    const count = picker.querySelector('[data-picker-count]');
    const max = parseInt(picker.dataset.max || '0', 10);
    const items = Array.from(picker.querySelectorAll('.pick'));
    items.forEach(function (item) { item._text = normalize(item.dataset.text); });

    function refresh() {
      const query = normalize(filter.value.trim());
      const subject = subjectSelect && subjectSelect.value ? ' ' + subjectSelect.value + ' ' : null;
      let checked = 0;
      items.forEach(function (item) {
        const box = item.querySelector('input');
        if (box.checked) checked++;
        item.classList.toggle('checked', box.checked);
        item.classList.toggle('match', !!subject && item.dataset.subjects.includes(subject));
        item.classList.toggle('filtered', !!query && !box.checked && !item._text.includes(query));
      });
      count.textContent = 'Đã chọn ' + checked + (max ? '/' + max : '');
      picker.classList.toggle('over', max > 0 && checked > max);
    }
    filter.addEventListener('input', refresh);
    picker.addEventListener('change', refresh);
    if (subjectSelect) subjectSelect.addEventListener('change', refresh);
    refresh();
  }

  function setupClassForm(form) {
    const frequency = form.querySelector('[name=frequency]');
    function toggle() {
      form.querySelectorAll('[data-freq]').forEach(function (block) {
        block.hidden = !block.dataset.freq.split(' ').includes(frequency.value);
      });
    }
    frequency.addEventListener('change', toggle);
    toggle();
    const subject = form.querySelector('[name=subject]');
    form.querySelectorAll('[data-picker]').forEach(function (p) { setupPicker(p, subject); });
  }

  function scrollToAnchor(root) {
    root.querySelectorAll('[data-scroll-today]').forEach(function (box) {
      const row = box.querySelector('[data-anchor]');
      const head = box.querySelector('thead');
      if (row) box.scrollTop = row.offsetTop - (head ? head.offsetHeight : 0);
    });
  }

  function initWidgets(root) {
    scrollToAnchor(root);
    setupDatePickers(root);
    root.querySelectorAll('form[data-class-form]').forEach(setupClassForm);
  }

  // Demo login page: clicking an account name fills in the form.
  function setupDemoLogin() {
    document.querySelectorAll('[data-demo-user]').forEach(function (button) {
      button.addEventListener('click', function () {
        document.getElementById('id_username').value = button.dataset.demoUser;
        document.getElementById('id_password').value = 'bluedragon123';
        button.closest('form').requestSubmit();
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    setupDemoLogin();
    setupMenu();
    if (document.getElementById('modal')) setupModal();
    setupCalendar();
    initWidgets(document);
  });
})();
