(() => {
  'use strict';

  const tablist = document.querySelector('.sw-crossing-tabs');
  const tabs = [...tablist.querySelectorAll('[data-crossing]')];
  const panels = tabs.map(tab => document.getElementById('crossing-' + tab.dataset.crossing));
  tablist.setAttribute('role', 'tablist');

  // With JavaScript off, the links lead to five fully visible sections.
  tabs.forEach((tab, index) => {
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', panels[index].id);
    panels[index].setAttribute('role', 'tabpanel');
    panels[index].setAttribute('aria-labelledby', tab.id);
    panels[index].tabIndex = 0;
  });

  function selectCrossing(index, { focus = false, updateUrl = false } = {}) {
    tabs.forEach((tab, i) => {
      const selected = i === index;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[i].hidden = !selected;
    });
    if (focus) tabs[index].focus({ preventScroll: true });
    if (updateUrl && location.hash !== tabs[index].hash) {
      history.pushState(null, '', tabs[index].hash);
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', event => {
      // Preserve opening the drawing section in a new tab with modifier keys.
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      selectCrossing(index, { updateUrl: true });
    });
    tab.addEventListener('keydown', event => {
      const offsets = { ArrowLeft: -1, ArrowRight: 1 };
      if (event.key === ' ') {
        event.preventDefault();
        selectCrossing(index, { updateUrl: true });
        return;
      }
      let next;
      if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else if (Object.hasOwn(offsets, event.key)) next = (index + offsets[event.key] + tabs.length) % tabs.length;
      else return;
      event.preventDefault();
      selectCrossing(next, { focus: true, updateUrl: true });
    });
  });

  function readCrossingHash() {
    const index = tabs.findIndex(tab => tab.hash === location.hash);
    if (index !== -1) selectCrossing(index);
  }

  selectCrossing(Math.max(0, tabs.findIndex(tab => tab.hash === location.hash)));
  window.addEventListener('hashchange', readCrossingHash);
  window.addEventListener('popstate', readCrossingHash);

  const links = [...document.querySelectorAll('.sw-page-nav a')];
  const sections = links.map(link => document.querySelector(link.hash));
  let framePending = false;
  function updatePageNavigation() {
    const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 5;
    let active = 0;
    sections.forEach((section, index) => {
      if (section.getBoundingClientRect().top <= 110) active = index;
    });
    if (atBottom) active = links.length - 1;
    links.forEach((link, index) => {
      if (index === active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
    framePending = false;
  }
  window.addEventListener('scroll', () => {
    if (!framePending) {
      framePending = true;
      requestAnimationFrame(updatePageNavigation);
    }
  }, { passive: true });
  window.addEventListener('resize', updatePageNavigation);
  updatePageNavigation();
})();
