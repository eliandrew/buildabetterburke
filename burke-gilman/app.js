(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const DATA = JSON.parse($('#map-data').textContent);
  const {sections, owners, areas} = DATA;
  const ownerById = Object.fromEntries(owners.map(o => [o.id, o]));
  const areaById = Object.fromEntries(areas.map(a => [a.id, a]));
  const sourceImage = $('#original-map').getAttribute('href');
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const ICONS = {
    'arrow-up-right':'<path d="M6 18L18 6M6 6h12v12"/>',
    print:'<path d="M7 8V3h10v5M7 16H4V9h16v7h-3M7 13h10v8H7Z"/><path d="M17 10h.01"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="M16 16l5 5"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    map:'<path d="M3 5l6-2 6 2 6-2v16l-6 2-6-2-6 2ZM9 3v16M15 5v16"/>',
    file:'<path d="M6 3h8l4 4v14H6ZM14 3v5h4M9 12h6M9 16h6"/>',
    expand:'<path d="M9 3H3v6M15 3h6v6M21 15v6h-6M9 21H3v-6"/>',
    'chevron-down':'<path d="M6 9l6 6 6-6"/>',
    'chevron-left':'<path d="M15 6l-6 6 6 6"/>',
    'chevron-right':'<path d="M9 6l6 6-6 6"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',minus:'<path d="M5 12h14"/>',
    fit:'<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M8 12h8M12 8v8"/>',
    locate:'<circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
    download:'<path d="M12 3v12M7 10l5 5 5-5M4 16v5h16v-5"/>',
    close:'<path d="M6 6l12 12M6 18L18 6"/>',
    image:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="M3 17l5-5 4 4 4-6 5 6"/>',
    idea:'<path d="M9 18h6M10 21h4M8 14a6 6 0 1 1 8 0l-1 2H9Z"/>'
  };
  const icon = name => '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">'+(ICONS[name] || ICONS.info)+'</svg>';
  const hydrateIcons = (root = document) => $$('[data-icon]', root).forEach(el => {el.innerHTML = icon(el.dataset.icon);});
  const TABS = [['overview','Overview'],['issue','Issues'],['idea','Ideas'],['people','People']];
  let current = sections[0], tab = 'overview', sourceMode = false;
  let hotspots = null;
  let visible = sections, suppressClickUntil = 0;
  let view = {x:120,y:-4,w:390,h:355}, homeView = true;
  const svg = $('#route-map'), canvas = $('#map-canvas');

  function ownerDot(owner) {return '<i class="owner-dot" style="--owner:'+owner.color+'" aria-hidden="true"></i>';}
  function matches(s) {
    const term = $('#search').value.trim().toLowerCase();
    const area = $('#area-filter').value, owner = $('#owner-filter').value;
    return (area==='all'||s.area===area) && (owner==='all'||s.owner===owner) && (!term || [s.number,s.name,ownerById[s.owner].name,ownerById[s.owner].short,areaById[s.area].name].join(' ').toLowerCase().includes(term));
  }
  function renderList() {
    visible = sections.filter(matches);
    const active = document.activeElement?.dataset.section;
    const scroll = {top:$('#section-list').scrollTop,left:$('#section-list').scrollLeft};
    let area = null;
    $('#section-list').innerHTML = visible.map(s => {
      let heading = '';
      if (s.area !== area) {
        area = s.area;
        const count = visible.filter(v => v.area === area).length;
        heading = '<div class="area-label">'+escape(areaById[area].name)+'<span>'+count+'</span></div>';
      }
      const owner = ownerById[s.owner];
      return heading+'<button class="section-item'+(s.id===current.id?' active':'')+'" data-section="'+s.id+'" aria-pressed="'+(s.id===current.id)+'" aria-label="Section '+s.number+', '+escape(s.name)+', '+escape(owner.name)+'"><span class="section-number">'+s.number+'</span><span class="section-text"><strong>'+escape(s.name)+'</strong><small>'+ownerDot(owner)+escape(owner.short)+'</small></span><span class="section-chevron">'+icon('chevron-right')+'</span></button>';
    }).join('');
    $('#section-list').scrollTop = scroll.top;
    $('#section-list').scrollLeft = scroll.left;
    if (active) $('.section-item[data-section="'+active+'"]')?.focus({preventScroll:true});
    $('#section-count').textContent = visible.length===sections.length?'62 sections':visible.length+' of 62';
    $('#empty-results').hidden = visible.length>0;
    $('#clear-filters').hidden = visible.length===sections.length && !$('#search').value && $('#area-filter').value==='all' && $('#owner-filter').value==='all';
    $$('.route-group').forEach(el => el.classList.toggle('filtered', !visible.some(s => s.id===el.dataset.section)));
    $('#selected-route').toggleAttribute('hidden',!visible.some(s=>s.id===current.id));
    renderMarkers();
  }
  function clearFilters() {
    $('#search').value='';$('#area-filter').value='all';$('#owner-filter').value='all';
    renderList();
  }
  function selectSection(id, options = {}) {
    const next = sections.find(s => s.id===id);
    if (!next) return;
    current=next;
    hotspots?.setSelectedArea(current.area);
    if (!matches(current)) clearFilters();
    if (options.hash!==false && location.hash!=='#'+id) {
      try {history.pushState(null,'','#'+id);} catch (_) {location.hash=id;}
    }
    renderList();renderDetail();renderSelection();
    if (options.zoom) focusSection();
    if (options.reveal) {
      const row=$('.section-item[data-section="'+id+'"]');
      const list=$('#section-list');
      if (row) {
        if (window.innerWidth<=1000) list.scrollLeft=row.offsetLeft-list.offsetLeft-(list.clientWidth-row.clientWidth)/2;
        else list.scrollTop += row.getBoundingClientRect().top-list.getBoundingClientRect().top-(list.clientHeight-row.clientHeight)/2;
      }
    }
    $('#announcement').textContent='Section '+current.number+': '+current.name+'. Owner shown: '+ownerById[current.owner].name+'.';
  }
  function renderDetail() {
    const requests = tab === 'requests' && hotspots;
    const areaIndex = areas.findIndex(area => area.id === current.area);
    $('#section-kicker').textContent=requests?'AREA '+(areaIndex+1)+' / '+areas.length:'SECTION '+current.number+' / 62';
    $('#section-title').textContent=requests?areaById[current.area].name:current.name;
    $('#section-subtitle').textContent=requests?'Nearby reports · approximate area summary':areaById[current.area].name+(current.small?' · Short ownership transition':'');
    $('#previous-section').disabled=requests?areaIndex===0:current===sections[0];
    $('#next-section').disabled=requests?areaIndex===areas.length-1:current===sections.at(-1);
    $('#previous-section').setAttribute('aria-label', requests?'Previous area':'Previous section');
    $('#next-section').setAttribute('aria-label', requests?'Next area':'Next section');
    $('#focus-section').innerHTML=icon('locate')+(requests?' Zoom to this area':' Zoom to this section');
    $('#detail-panel').setAttribute('aria-label', requests?'Selected trail area request summary':'Selected section');
    $('.detail-tabs').innerHTML=TABS.map(([id,name]) =>
      '<button role="tab" id="tab-'+id+'" aria-controls="detail-content" aria-selected="'+(id===tab)+'" tabindex="'+(id===tab?'0':'-1')+'" data-tab="'+id+'">'+name+'</button>'
    ).join('');
    $('#detail-content').setAttribute('aria-labelledby','tab-'+tab);
    renderContent();
    $('#detail-content').scrollTop=0;
  }
  function promptCard(label,title,body,link) {
    return '<article class="prompt-card"><span class="prompt-label">'+escape(label)+'</span><h4>'+escape(title)+'</h4><p>'+escape(body)+'</p>'+(link?'<a href="'+escape(link)+'" target="_blank" rel="noopener noreferrer">Visit organization website '+icon('arrow-up-right')+'</a>':'')+'</article>';
  }
  function preview() {
    const [x0,y0,x1,y1]=current.bounds;
    const w=Math.max(x1-x0+14,(y1-y0+14)*2.15,38),h=w/2.15;
    const cx=(x0+x1)/2,cy=(y0+y1)/2;
    return '<button class="source-preview" data-preview-source aria-label="View original parcel map for section '+current.number+'"><svg viewBox="'+[cx-w/2,cy-h/2,w,h].join(' ')+'" aria-hidden="true"><image x="0" y="0" width="612" height="792" href="'+sourceImage+'"/></svg><span>'+icon('file')+' Original map · section '+current.number+'</span></button><p class="source-note">PDF colors and linework. Area names on this page are approximate.</p>';
  }
  function adjacentSections() {
    const index=sections.indexOf(current);
    return [index-1,index+1].filter(i => i>=0 && i<sections.length).map(i => {
      const s=sections[i],owner=ownerById[s.owner];
      const gap=(index===0&&i===1)||(index===1&&i===0);
      return '<button class="adjacent" data-adjacent="'+s.id+'">'+ownerDot(owner)+'<span>'+s.number+' · '+escape(s.name)+'<small>'+escape(owner.short)+(gap?' · separated by a gap in the source':'')+'</small></span>'+icon(i<index?'chevron-left':'chevron-right')+'</button>';
    }).join('');
  }
  function renderContent() {
    const owner=ownerById[current.owner],area=areaById[current.area];
    let html='';
    if (tab==='requests' && hotspots) {
      html=hotspots.renderDetails(current.area);
    } else if (tab==='overview') {
      html='<div class="owner-card"><div class="eyebrow"><span class="owner-swatch" style="--owner:'+owner.color+'"></span> OWNER SHOWN IN THE MAP</div><h3>'+escape(owner.name)+'</h3><p>'+(current.owner==='private'?'The source combines private and unknown ownership.':'Ownership category transcribed from the PDF legend.')+'</p></div>';
      html+='<p class="section-description">'+escape(area.description)+'</p>';
      if (current.small) html+='<p class="source-note">A short color change in the source, retained as its own section. Zoom in to inspect it.</p>';
      html+='<div class="detail-meta"><div><span>Map reference</span><strong>Page 1 · section '+current.number+'</strong></div><div><span>Maintenance contact</span><strong>To be confirmed</strong></div><div><span>Parcel ID / exact limits</span><strong>Not supplied</strong></div></div>';
      html+='<div class="discussion-card"><div class="eyebrow">'+icon('idea')+' THE QUESTION TO EXPLORE</div><p>'+escape(area.question)+'</p></div>';
      html+='<h3>NEIGHBORING SECTIONS</h3>'+adjacentSections()+preview();
    } else if (tab==='issue') {
      html='<p class="tab-intro">Questions to investigate, not confirmed defects.</p>';
      html+=promptCard('To investigate','Ownership and responsibility',owner.context);
      html+=promptCard('To investigate',current.small?'Check this short transition':'Continuity and access',current.small?'Locate the color change on the original map. Check the corresponding place on site before assuming it is a street crossing, boundary, or maintenance handoff.':'Record trail entrances, crossings, usable width, surface changes, and wayfinding. The ownership map does not establish current trail condition.');
      if(current.area==='ballard') html+=promptCard('Source limitation','The gap in Ballard','The PDF does not draw a continuous trail between its two western mapped reaches. Confirm current routing and ownership using parcel and project records; do not infer either from this map.');
      if(current.owner==='private') html+=promptCard('Needs records','Private—or not identified?','The source uses one black category for private and unknown ownership. Establish the parcel and land interest before naming an owner or drawing conclusions about public access.');
    } else if (tab==='idea') {
      html='<p class="tab-intro">Discussion starters for this area. These are possibilities to explore, not approved projects.</p>';
      area.ideas.forEach((idea,i)=>{html+=promptCard('Suggested next step',i===0?'Take a closer look':'Connect the pieces',idea);});
    } else if (tab==='people') {
      html='<p class="tab-intro">Suggested contacts and perspectives. No contact, participation, or endorsement is implied.</p>';
      html+=promptCard('Ownership lead',owner.name,owner.context,owner.url);
      html+=promptCard('People to include','Everyday trail users','Include people walking, rolling, cycling, using mobility devices, and reaching nearby destinations. Hear from both through-travelers and neighbors.');
      html+=promptCard('Coordination','Adjacent owners and maintenance teams','Use the neighboring sections to identify possible handoffs. Confirm the actual maintenance and access agreements before assigning responsibility.');
    }
    $('#detail-content').innerHTML=html;
  }
  function selectTab(next, focus=true) {
    if (!TABS.some(([id])=>id===next)) return;
    tab=next;renderDetail();
    if(focus) $('#tab-'+tab).focus({preventScroll:true});
  }

  function renderMap() {
    // Paths retain their original PDF coordinates and disconnected subpaths.
    // Draw long reaches first so short transitions receive the topmost hit area.
    $('#trail-sections').innerHTML=[...sections].sort((a,b)=>b.mapLength-a.mapLength).map(s => {
      const paths=s.paths.join(' ');
      return '<g class="route-group" data-section="'+s.id+'" style="--owner:'+ownerById[s.owner].color+'"><path class="route-underlay" d="'+paths+'"/><path class="route-line" d="'+paths+'"/><path class="route-hit" d="'+paths+'"><title>Section '+s.number+': '+escape(s.name)+' — '+escape(ownerById[s.owner].name)+'</title></path></g>';
    }).join('');
  }
  function renderSelection() {
    const paths=(hotspots?.active?sections.filter(s=>s.area===current.area).flatMap(s=>s.paths):current.paths).join(' ');
    const hotspotColor=hotspots?.colorForArea(current.area)||'';
    $('#selected-route').innerHTML='<g style="--owner:'+ownerById[current.owner].color+';--hotspot:'+hotspotColor+'"><path class="selection-edge" d="'+paths+'"/><path class="selection-halo" d="'+paths+'"/><path class="selection-line" d="'+paths+'"/></g>';
    renderMarkers();
  }
  function renderMarkers() {
    if (!svg.getScreenCTM()) return;
    const focused = document.activeElement?.closest('.map-marker')?.dataset.section;
    const scale=1/svg.getScreenCTM().a;
    const chosen=visible.some(s=>s.id===current.id)?[current]:[];
    const minDistance=36*scale;
    const candidates=[...visible].filter(s => s.id!==current.id && s.mapLength/scale>35).sort((a,b)=>b.mapLength-a.mapLength);
    for(const s of candidates) {
      if(s.midpoint[0]<view.x||s.midpoint[0]>view.x+view.w||s.midpoint[1]<view.y||s.midpoint[1]>view.y+view.h) continue;
      if(chosen.every(p=>Math.hypot(p.midpoint[0]-s.midpoint[0],p.midpoint[1]-s.midpoint[1])>minDistance)) chosen.push(s);
    }
    $('#map-markers').innerHTML=chosen.reverse().map(s => {
      const selected=s.id===current.id,offset=selected&&s.small?30:0;
      return '<g class="map-marker'+(selected?' active':'')+'" data-section="'+s.id+'" transform="translate('+[s.midpoint[0],s.midpoint[1]-offset*scale].join(' ')+') scale('+scale+')" role="button" tabindex="0" aria-label="Section '+s.number+', '+escape(s.name)+', '+escape(ownerById[s.owner].name)+'" aria-pressed="'+selected+'">'+(offset?'<path d="M0 17V30" stroke="#c5522e" fill="none"/><circle cy="30" r="3" style="fill:#fffefa;stroke:#c5522e;stroke-width:1.5"/>':'')+(selected?'<circle class="marker-halo" r="18"/>':'')+'<circle r="'+(selected?15:12)+'"/><text>'+s.number+'</text></g>';
    }).join('');
    if (focused) ($('.map-marker[data-section="'+focused+'"]') || canvas).focus({preventScroll:true});
  }
  function applyView() {
    svg.setAttribute('viewBox',[view.x,view.y,view.w,view.h].join(' '));
    const matrix=svg.getScreenCTM();
    if(matrix) {
      const scale=1/matrix.a;
      const compact=canvas.clientWidth<450&&view.w>180;
      $$('#map-labels text').forEach(label=>{
        if(!label.dataset.fulltext) label.dataset.fulltext=label.textContent;
        const full=label.dataset.fulltext;
        label.style.display=compact&&['WALLINGFORD','BRYANT','LAURELHURST','Ballard Locks area'].includes(full)?'none':'';
        label.textContent=compact?({'UNIVERSITY DISTRICT':'UW','Northern map edge':'Map edge','Gap in the source':'Source gap'}[full]||full):full;
        const size=(label.classList.contains('water-label')?19:label.classList.contains('small-water')?11:label.classList.contains('place-label')?8:9)*(compact?.8:1);
        label.style.fontSize=size*scale+'px';
        label.style.strokeWidth=3*scale+'px';
        label.style.letterSpacing=(label.classList.contains('neighborhood')?1.25:.1)*scale+'px';
      });
    }
    renderMarkers();
  }
  function fitBounds(bounds, minWidth=38, padding=70) {
    const rect=canvas.getBoundingClientRect();
    if (rect.width<=0 || rect.height<=0) return;
    const aspect=rect.width/rect.height;
    const [x0,y0,x1,y1]=bounds;
    const w=Math.max(minWidth,(x1-x0)/Math.max(.4,1-2*padding/rect.width),(y1-y0)/Math.max(.4,1-2*padding/rect.height)*aspect);
    const h=w/aspect;
    view={x:(x0+x1-w)/2,y:(y0+y1-h)/2,w,h};applyView();
  }
  function fitMap() {homeView=true;fitBounds([152,26,457,302],350,canvas.clientWidth<450?38:78);}
  function focusArea(id) {
    const areaSections=sections.filter(s=>s.area===id);
    if(!areaSections.length) return;
    homeView=false;
    fitBounds([Math.min(...areaSections.map(s=>s.bounds[0])),Math.min(...areaSections.map(s=>s.bounds[1])),Math.max(...areaSections.map(s=>s.bounds[2])),Math.max(...areaSections.map(s=>s.bounds[3]))],65,75);
  }
  function focusSection() {if(tab==='requests'&&hotspots) {focusArea(current.area);return;}homeView=false;fitBounds(current.bounds,36,100);}
  function point(x,y) {return new DOMPoint(x,y).matrixTransform(svg.getScreenCTM().inverse());}
  function zoom(factor, anchor) {
    homeView=false;
    const w=Math.max(12,Math.min(900,view.w*factor));factor=w/view.w;
    const pivot=anchor||{x:view.x+view.w/2,y:view.y+view.h/2};
    view={x:pivot.x-(pivot.x-view.x)*factor,y:pivot.y-(pivot.y-view.y)*factor,w,h:view.h*factor};applyView();
  }
  function setSourceMode(on) {
    if(on && hotspots?.active) hotspots.setActive(false);
    sourceMode=on;
    $('#original-map').toggleAttribute('hidden',!on);
    $('#styled-base').toggleAttribute('hidden',on);
    $('.map-panel').classList.toggle('source-background',on);
    $('#map-mode').setAttribute('aria-pressed',String(!on));
    $('#source-mode').setAttribute('aria-pressed',String(on));
    $('#map-caption').textContent=on?'Original PDF · selectable ownership overlay':'Ownership from the supplied parcel map';
  }
  function openImage(src,title,caption) {
    $('#full-source-image').src=src;$('#full-source-image').alt=title;
    $('#source-image-title').textContent=title;$('#source-image-caption').textContent=caption;
    $('#source-image-dialog').showModal();$('#source-image-dialog').scrollTop=0;
  }
  function download(blob,name) {
    const url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
  $('#detail-content').addEventListener('click',event => {
    const adjacent=event.target.closest('[data-adjacent]');
    if(adjacent) {selectSection(adjacent.dataset.adjacent,{zoom:true,reveal:true});$('#section-title').scrollIntoView({block:'nearest'});return;}
    if(event.target.closest('[data-preview-source]')) {setSourceMode(true);focusSection();if(window.innerWidth<=680) canvas.scrollIntoView({block:'center'});return;}
  });
  $('.detail-tabs').addEventListener('click',event=>{const b=event.target.closest('[data-tab]');if(b) selectTab(b.dataset.tab);});
  $('.detail-tabs').addEventListener('keydown',event => {
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();const i=TABS.findIndex(([id])=>id===tab);
    const next=event.key==='Home'?0:event.key==='End'?TABS.length-1:(i+(event.key==='ArrowRight'?1:-1)+TABS.length)%TABS.length;
    selectTab(TABS[next][0]);
  });
  $('#section-list').addEventListener('click',event => {
    const button=event.target.closest('[data-section]');if(!button) return;
    selectSection(button.dataset.section,{zoom:true});
    $('.section-item[data-section="'+current.id+'"]')?.focus({preventScroll:true});
  });
  function hoverSection(id) {$$('.route-group').forEach(g=>g.classList.toggle('hovered',g.dataset.section===id));}
  $('#section-list').addEventListener('pointerover',event=>hoverSection(event.target.closest('[data-section]')?.dataset.section));
  $('#section-list').addEventListener('pointerleave',()=>hoverSection(null));
  $('#search').addEventListener('input',()=>{renderList();$('#announcement').textContent=visible.length+' matching sections.';});
  $('#area-filter').addEventListener('change',()=>{
    renderList();
    if(visible.length&&!matches(current)) selectSection(visible[0].id,{reveal:true});
    if(visible.length) {homeView=false;fitBounds([Math.min(...visible.map(s=>s.bounds[0])),Math.min(...visible.map(s=>s.bounds[1])),Math.max(...visible.map(s=>s.bounds[2])),Math.max(...visible.map(s=>s.bounds[3]))],65,85);}
  });
  $('#owner-filter').addEventListener('change',()=>{
    renderList();
    if(visible.length&&!matches(current)) selectSection(visible[0].id,{reveal:true});
    if(visible.length===1) focusSection();else fitMap();
  });
  $('#clear-filters').addEventListener('click',()=>{clearFilters();fitMap();});
  function navigateDetail(direction) {
    if(tab==='requests'&&hotspots) {
      const area=areas[areas.findIndex(a=>a.id===current.area)+direction];
      if(area) selectSection(sections.find(s=>s.area===area.id).id,{zoom:true});
    } else selectSection(sections[sections.indexOf(current)+direction]?.id,{zoom:true,reveal:true});
  }
  $('#previous-section').addEventListener('click',()=>navigateDetail(-1));
  $('#next-section').addEventListener('click',()=>navigateDetail(1));
  $('#focus-section').addEventListener('click',()=>{focusSection();if(window.innerWidth<=680) canvas.scrollIntoView({block:'center'});});
  $('#map-mode').addEventListener('click',()=>{hotspots?.setActive(false);setSourceMode(false);});
  $('#source-mode').addEventListener('click',()=>{hotspots?.setActive(false);setSourceMode(true);});
  $('#zoom-in').addEventListener('click',()=>zoom(.75));$('#zoom-out').addEventListener('click',()=>zoom(1/.75));
  $('#fit-map').addEventListener('click',fitMap);
  $('#expand-map').addEventListener('click',()=>{
    const on=$('#workspace').classList.toggle('expanded');
    $('#expand-map').setAttribute('aria-label',on?'Restore section panels':'Expand map');
    $('#expand-map').setAttribute('title',on?'Restore section panels':'Expand map');
    $('#expand-map').setAttribute('aria-pressed',String(on));
  });
  $('#print-map').addEventListener('click',()=>window.print());
  $$('[data-open-source]').forEach(b=>b.addEventListener('click',()=>{$('#source-dialog').showModal();$('#source-dialog').scrollTop=0;}));
  $('#view-source-page').addEventListener('click',()=>openImage(sourceImage,'Original parcel ownership map','Parcel Ownership Map_Trails-2.pdf · page 1. Full original map, including the ownership key.'));
  $('#download-source').addEventListener('click',()=>{
    const binary=atob($('#pdf-data').textContent.trim());
    const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
    download(new Blob([bytes],{type:'application/pdf'}),DATA.source.filename);
  });
  $$('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
  $$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{
    if(event.target!==dialog) return;
    const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom) dialog.close();
  }));

  const pointers=new Map();let drag=null,pinch=null;
  canvas.addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY>0?1.1:1/1.1,point(event.clientX,event.clientY));},{passive:false});
  canvas.addEventListener('pointerdown',event=>{
    if(event.button!==0) return;
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    canvas.setPointerCapture(event.pointerId);
    if(pointers.size===1) drag={x:event.clientX,y:event.clientY,view:{...view},matrix:svg.getScreenCTM().inverse(),moved:false,target:event.target.closest('[data-section]')?.dataset.section};
    if(pointers.size===2) {const [a,b]=[...pointers.values()];pinch={distance:Math.hypot(a.x-b.x,a.y-b.y)};suppressClickUntil=Date.now()+500;}
  });
  canvas.addEventListener('pointermove',event=>{
    if(!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
    if(pointers.size===2&&pinch) {
      const [a,b]=[...pointers.values()],distance=Math.hypot(a.x-b.x,a.y-b.y);
      if(distance>0&&pinch.distance>0) zoom(pinch.distance/distance,point((a.x+b.x)/2,(a.y+b.y)/2));
      pinch.distance=distance;suppressClickUntil=Date.now()+500;return;
    }
    if(!drag||pinch) return;
    if(Math.hypot(event.clientX-drag.x,event.clientY-drag.y)>4) drag.moved=true;
    if(drag.moved) {
      const start=new DOMPoint(drag.x,drag.y).matrixTransform(drag.matrix),now=new DOMPoint(event.clientX,event.clientY).matrixTransform(drag.matrix);
      homeView=false;view={...drag.view,x:drag.view.x-(now.x-start.x),y:drag.view.y-(now.y-start.y)};applyView();canvas.classList.add('dragging');suppressClickUntil=Date.now()+300;
    }
  });
  function endPointer(event) {
    const id=drag?.target;
    const clicked=event.type==='pointerup'&&pointers.size===1&&!drag?.moved&&!pinch&&Date.now()>suppressClickUntil;
    pointers.delete(event.pointerId);
    if(!pointers.size) {drag=null;pinch=null;canvas.classList.remove('dragging');}
    else if(pinch) {drag=null;}
    if(clicked&&id) selectSection(id,{reveal:true});
  }
  canvas.addEventListener('pointerup',endPointer);canvas.addEventListener('pointercancel',endPointer);
  window.addEventListener('blur',()=>{pointers.clear();drag=null;pinch=null;canvas.classList.remove('dragging');});
  canvas.addEventListener('keydown',event=>{
    if((event.key==='Enter'||event.key===' ')&&event.target.closest('[data-section]')) {
      event.preventDefault();const id=event.target.closest('[data-section]').dataset.section;selectSection(id,{reveal:true});$('.map-marker[data-section="'+id+'"]')?.focus({preventScroll:true});return;
    }
    if(!['+','=','-','0','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    if(event.key==='+'||event.key==='=') zoom(.75);else if(event.key==='-') zoom(1/.75);else if(event.key==='0') fitMap();
    else {homeView=false;if(event.key==='ArrowLeft')view.x-=view.w*.08;if(event.key==='ArrowRight')view.x+=view.w*.08;if(event.key==='ArrowUp')view.y-=view.h*.08;if(event.key==='ArrowDown')view.y+=view.h*.08;applyView();}
  });
  function readHash() {
    const id=location.hash.slice(1),found=sections.some(s=>s.id===id);
    selectSection(found?id:sections[0].id,{hash:false,zoom:found,reveal:found});
  }
  window.addEventListener('hashchange',readHash);
  window.addEventListener('popstate',readHash);
  new ResizeObserver(()=>{
    if (canvas.clientWidth<=0 || canvas.clientHeight<=0) return;
    if(homeView) fitMap();
    else {const center=view.y+view.h/2;view.h=view.w/(canvas.clientWidth/canvas.clientHeight);view.y=center-view.h/2;applyView();}
  }).observe(canvas);
  areas.forEach(a=>$('#area-filter').add(new Option(a.name,a.id)));
  owners.forEach(o=>$('#owner-filter').add(new Option(o.short,o.id)));
  $('#owner-legend').innerHTML=owners.map(o=>'<span class="legend-item" title="'+escape(o.name)+'"><i style="--owner:'+o.color+'"></i>'+escape(o.short)+'</span>').join('');
  const compactLayout=matchMedia('(max-width:680px)');
  $('.map-legend').open=!compactLayout.matches;
  compactLayout.addEventListener('change',event=>{$('.map-legend').open=!event.matches;});
  hotspots=window.createBurkeHotspots?.({
    sections,areas,
    onSelectArea(id) {
      const section=sections.find(s=>s.area===id);
      if(!section) return;
      tab='requests';
      selectSection(section.id,{zoom:true});
      $('#announcement').textContent=areaById[id].name+'. Request summary updated.';
      if(window.innerWidth<=680) $('#map-canvas').scrollIntoView({block:'center'});
    },
    onModeChange(on) {
      if(on) clearFilters();
      tab=on?'requests':'overview';
      setSourceMode(false);
      renderDetail();renderSelection();
    },
    onDataChange() {if(tab==='requests') renderContent();renderSelection();}
  })||null;
  if(hotspots) TABS.splice(1,0,['requests','Requests']);
  hydrateIcons();renderMap();fitMap();readHash();renderSelection();
  if(hotspots) hotspots.setActive(true);
})();
