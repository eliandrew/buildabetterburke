/* Area-level request summaries. The parcel PDF is not used to locate requests. */
(() => {
  'use strict';
  window.createBurkeHotspots = ({sections, areas, onSelectArea, onModeChange, onDataChange}) => {
    const data = window.BURKE_REQUEST_HOTSPOTS;
    if (!data || data.schemaVersion !== 1 || !Array.isArray(data.rows) || !data.periods?.length || !data.areas?.length) return null;
    const $ = selector => document.querySelector(selector);
    const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const format = value => Number(value).toLocaleString('en-US');
    const decimal = value => Number(value).toLocaleString('en-US', {maximumFractionDigits:1});
    const date = value => new Date(value + 'T12:00:00Z').toLocaleDateString('en-US', {month:'short', day:'numeric', year:'numeric', timeZone:'UTC'});
    const areaData = areas.map(area => ({...area, ...data.areas.find(item => item.id === area.id)}));
    const areaById = Object.fromEntries(areaData.map(area => [area.id, area]));
    const state = {active:false, period:data.periods.some(p => p.id === 'recent') ? 'recent' : data.periods[0].id, channel:'app', type:'all', selected:sections[0].area};
    const buckets = [
      {max:0, color:'#a9b6ad', label:'0'},
      {max:100, color:'#a89557', label:'>0–100'},
      {max:250, color:'#d68538', label:'>100–250'},
      {max:500, color:'#c45430', label:'>250–500'},
      {max:Infinity, color:'#873525', label:'>500'}
    ];
    const color = value => Number.isFinite(value) ? buckets.find(bucket => value <= bucket.max).color : '#a9b6ad';
    let totals = [], filteredRows = [];
    const period = () => data.periods.find(item => item.id === state.period);
    const intakeLabel = () => state.channel === 'app' ? 'Find It, Fix It app' : 'All intake channels';
    const links = '<a href="https://www.seattle.gov/customer-service-bureau/find-it-fix-it-mobile-app" target="_blank" rel="noopener noreferrer">Report with Find It, Fix It ↗</a><a href="https://data.seattle.gov/City-Administration/Customer-Service-Requests/5ngg-rpne" target="_blank" rel="noopener noreferrer">Seattle source dataset ↗</a><a href="request-hotspots-methodology.html">Methods &amp; coverage notes</a>';

    const toggle = document.createElement('button');
    toggle.id = 'hotspot-mode';
    toggle.type = 'button';
    toggle.setAttribute('aria-pressed', 'false');
    toggle.innerHTML = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c1 5 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 3 2 3 2 3s3-3 1-9Z"/></svg> Hot spots';
    $('#source-mode').before(toggle);
    $('#map-mode').innerHTML = '<span data-icon="map"></span> Ownership';
    $('.segmented').setAttribute('aria-label', 'Map view');

    const rail = document.createElement('div');
    rail.className = 'hotspot-rail';
    rail.hidden = true;
    rail.innerHTML = '<div class="hotspot-rail-heading"><span class="eyebrow">REQUEST HOT SPOTS</span><span class="hotspot-snapshot">Snapshot · '+escape(date(data.source.snapshotDate))+'</span><h2>Where reports cluster.</h2><p>Compare nearby requests across eight trail areas.</p></div>'+
      '<div class="hotspot-filters"><label>Period<select id="hotspot-period">'+data.periods.map(item => '<option value="'+escape(item.id)+'">'+escape(item.label)+'</option>').join('')+'</select></label>'+
      '<label>Intake<select id="hotspot-channel"><option value="app">Find It, Fix It app only</option><option value="all">All intake channels</option></select></label>'+
      '<label>Request type<select id="hotspot-type"><option value="all">All request types</option>'+[...new Set(data.rows.map(row => row[3]))].sort((a,b) => a.localeCompare(b)).map(type => '<option value="'+escape(type)+'">'+escape(type)+'</option>').join('')+'</select></label></div>'+
      '<div class="hotspot-summary" id="hotspot-summary" aria-live="polite" aria-atomic="true"></div>'+
      '<div class="hotspot-ranking-heading"><span>AREA · RANKED BY REPORT DENSITY</span><span>Requests / km</span></div><div id="hotspot-area-list" class="hotspot-area-list" aria-label="Trail areas ranked by requests per kilometer"></div>'+
      '<p class="hotspot-rail-note">Report volume, not severity. A 50 m trail buffer includes nearby streets and properties. Seattle coverage only.</p>';
    $('.route-nav').append(rail);
    $('#hotspot-period').value = state.period;

    const legend = document.createElement('details');
    legend.className = 'map-legend hotspot-legend';
    legend.hidden = true;
    legend.open = !matchMedia('(max-width:680px)').matches;
    legend.innerHTML = '<summary>Requests per mapped km <span aria-hidden="true">⌄</span></summary><div class="hotspot-legend-scale">'+buckets.map(bucket => '<span><i style="background:'+bucket.color+'"></i>'+bucket.label+'</span>').join('')+'</div><p>Same color across each approximate area.<br>Area summaries, not individual report locations.</p>';
    $('.map-panel').append(legend);

    const note = document.createElement('div');
    note.className = 'hotspot-context';
    note.innerHTML = '<div><span class="eyebrow">COMMUNITY REPORTS ALONG THE TRAIL</span><p>Find It, Fix It requests near the trail <span>· 50 m corridor · Seattle data</span></p></div><div class="hotspot-context-links"><a href="https://www.seattle.gov/customer-service-bureau/find-it-fix-it-mobile-app" target="_blank" rel="noopener noreferrer">Report an issue ↗</a><a href="request-hotspots-methodology.html">How we counted</a></div>';
    $('#workspace').before(note);

    function calculate() {
      filteredRows = data.rows.filter(row => row[1] === state.period && (state.channel === 'all' || row[2] === state.channel) && (state.type === 'all' || row[3] === state.type));
      const counts = Object.fromEntries(areaData.map(area => [area.id, 0]));
      for (const row of filteredRows) if (Object.hasOwn(counts, row[0])) counts[row[0]] += row[5];
      totals = areaData.map(area => ({...area, count:counts[area.id], rate:area.lengthKm > 0 ? counts[area.id] / area.lengthKm : null})).sort((a,b) => (b.rate ?? -1) - (a.rate ?? -1) || b.count - a.count || a.name.localeCompare(b.name));
    }
    function renderRanking() {
      const total = totals.reduce((sum, area) => sum + area.count, 0);
      const max = Math.max(...totals.map(area => area.rate || 0), 1);
      $('#hotspot-summary').innerHTML = '<strong>'+format(total)+'</strong><span>near-trail requests<br><small>'+escape(period().label)+' · '+escape(intakeLabel())+'</small></span>';
      $('#hotspot-area-list').innerHTML = totals.map((area, index) => {
        const rate = area.rate === null ? '—' : decimal(area.rate);
        return '<button type="button" class="hotspot-area'+(state.selected === area.id ? ' active' : '')+'" data-hotspot-area="'+escape(area.id)+'" aria-pressed="'+(state.selected === area.id)+'" aria-label="'+escape(area.name)+': '+format(area.count)+' requests, '+rate+' per mapped kilometer" style="--hotspot:'+color(area.rate)+';--bar:'+((area.rate || 0) / max * 100)+'%"><span class="hotspot-rank">'+(index+1)+'</span><span class="hotspot-area-body"><strong>'+escape(area.name)+'</strong><span class="hotspot-bar"><i></i></span><small>'+format(area.count)+' requests · '+(area.lengthKm > 0 ? decimal(area.lengthKm)+' km' : 'length unavailable')+'</small></span><span class="hotspot-rate">'+rate+'</span></button>';
      }).join('');
    }
    function syncMap() {
      for (const group of document.querySelectorAll('.route-group')) {
        const section = sections.find(item => item.id === group.dataset.section);
        const total = totals.find(item => item.id === section.area);
        group.style.setProperty('--hotspot', color(total?.rate));
        const title = group.querySelector('title');
        if (!title.dataset.ownershipTitle) title.dataset.ownershipTitle = title.textContent;
        title.textContent = state.active && total ? total.name+' area: '+format(total.count)+' requests; '+decimal(total.rate)+' per mapped km. Approximate area summary.' : title.dataset.ownershipTitle;
      }
      if (state.active) $('#map-caption').textContent = 'Request density by area · '+period().label;
      $('#map-mode').setAttribute('aria-pressed', String(!state.active && $('#source-mode').getAttribute('aria-pressed') !== 'true'));
    }
    function update() {
      calculate();
      renderRanking();
      syncMap();
      onDataChange();
    }
    function setActive(active) {
      state.active = active;
      $('#workspace').classList.toggle('hotspots-active', active);
      $('.map-panel').classList.toggle('hotspot-mode', active);
      rail.hidden = !active;
      legend.hidden = !active;
      toggle.setAttribute('aria-pressed', String(active));
      $('.route-nav').setAttribute('aria-label', active ? 'Near-trail request summaries by area' : 'Trail sections');
      $('#map-canvas').setAttribute('aria-label', active ? 'Interactive request density map by approximate trail area. Use the ranked area buttons to select an area. Plus and minus zoom, arrow keys pan, and zero fits the trail.' : 'Interactive ownership map. Plus and minus zoom, arrow keys pan, and zero fits the trail. Use the section list to select every section, including very short transitions.');
      onModeChange(active);
      syncMap();
    }
    function breakdown(rows, index) {
      const counts = new Map();
      for (const row of rows) counts.set(row[index] || 'Not specified', (counts.get(row[index] || 'Not specified') || 0) + row[5]);
      return [...counts].sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    }
    function breakdownHTML(entries) {
      const max = Math.max(...entries.map(item => item[1]), 1);
      return '<dl class="hotspot-breakdown">'+entries.map(([label, count]) => '<div><dt>'+escape(label)+'</dt><dd>'+format(count)+'</dd><span aria-hidden="true" style="--bar:'+(count / max * 100)+'%"></span></div>').join('')+'</dl>';
    }
    function renderDetails(areaId) {
      const area = totals.find(item => item.id === areaId);
      if (!area) return '<p>No request summary is available for this area.</p>';
      const rows = filteredRows.filter(row => row[0] === areaId);
      const types = breakdown(rows, 3), statuses = breakdown(rows, 4);
      const selectedPeriod = period();
      let html = '<div class="request-detail-scope"><span class="eyebrow">'+escape(intakeLabel())+'</span><p>'+escape(date(selectedPeriod.start))+' – '+escape(date(selectedPeriod.end))+'</p></div>'+
        '<div class="request-metrics"><div><strong>'+format(area.count)+'</strong><span>requests near this area</span></div><div><strong>'+decimal(area.rate ?? 0)+'</strong><span>per mapped km</span></div></div>'+
        '<p class="request-area-length">'+decimal(area.lengthKm || 0)+' km of mapped trail · '+escape(state.type === 'all' ? 'All request types' : state.type)+'</p>'+
        '<p class="request-boundary">'+escape(area.boundaryDescription || 'An approximate trail area; see the methodology for its boundaries.')+'</p>';
      if (!area.count) html += '<p class="request-empty">No matching requests in this snapshot. This does not establish that the area has no issues.</p>';
      else {
        html += '<h3>REQUEST TYPES</h3>'+breakdownHTML(types.slice(0, 6));
        if (types.length > 6) html += '<details class="request-more"><summary>See '+(types.length - 6)+' more request types</summary>'+breakdownHTML(types.slice(6))+'</details>';
        html += '<h3>STATUS AT EXPORT</h3>'+breakdownHTML(statuses)+'<p class="request-status-note">Statuses are shown as recorded by Seattle. A status does not independently verify current conditions or a completed repair.</p>';
      }
      html += '<div class="request-caution"><strong>What these hot spots mean</strong><p>Reports within 50 m of the mapped trail centerline, including nearby streets and properties. Counts measure reporting activity, not danger, severity, or confirmed trail defects.</p><p>These are approximate area summaries, not exact report locations or assignments of ownership or maintenance responsibility. Seattle requests only; coverage does not continue outside the city. 2026 is a partial year.</p></div>'+
        '<div class="request-links">'+links+(areaId === 'uw' ? '<a href="https://facilities.uw.edu/services/requests" target="_blank" rel="noopener noreferrer">UW Facilities service requests ↗</a><p class="request-status-note">Requests made directly to UW are not necessarily included in Seattle’s dataset.</p>' : '')+'<a href="https://www.seattle.gov/parks/parks/burke-gilman-trail" target="_blank" rel="noopener noreferrer">Seattle Parks trail information ↗</a></div>';
      return html;
    }
    toggle.addEventListener('click', () => setActive(true));
    rail.addEventListener('click', event => {
      const button = event.target.closest('[data-hotspot-area]');
      if (button) onSelectArea(button.dataset.hotspotArea);
    });
    for (const field of ['period','channel','type']) $('#hotspot-'+field).addEventListener('change', event => {state[field] = event.target.value; update();});
    calculate();
    renderRanking();
    return {
      get active() { return state.active; },
      setActive,
      renderDetails,
      colorForArea: id => color(totals.find(area => area.id === id)?.rate),
      areaById,
      setSelectedArea(id) {
        state.selected = id;
        for (const button of rail.querySelectorAll('[data-hotspot-area]')) {
          const selected = button.dataset.hotspotArea === id;
          button.classList.toggle('active', selected);
          button.setAttribute('aria-pressed', String(selected));
        }
      }
    };
  };
})();
