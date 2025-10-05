document.addEventListener('DOMContentLoaded', () => {
  // theme toggle
  const themeToggle = document.getElementById('theme-toggle');
  const root = document.documentElement;
  const saved = localStorage.getItem('site-theme') || 'dark';
  root.setAttribute('data-theme', saved);
  if(themeToggle){
    themeToggle.addEventListener('click', () => {
      const cur = root.getAttribute('data-theme');
      const next = cur === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('site-theme', next);
    });
  }

  // search
  const searchBtn = document.getElementById('search-btn');
  const searchInput = document.getElementById('top-search');
  if(searchBtn){
    searchBtn.addEventListener('click', () => {
      const q = encodeURIComponent(searchInput.value.trim());
      window.location = `/?q=${q}`;
    });
    searchInput.addEventListener('keyup', (e) => {
      if(e.key === 'Enter') searchBtn.click();
    });
  }

  // View buttons -> modal
  const bindViewButtons = () => {
    document.querySelectorAll('.view-btn').forEach(btn => {
      btn.onclick = async () => {
        const id = btn.dataset.id;
        const res = await fetch(`/api/movie/${id}`);
        if(!res.ok) return;
        const m = await res.json();
        showModal(m);
      };
    });
  };
  bindViewButtons();

  // modal functions
  const modal = document.getElementById('movie-modal');
  const modalContent = document.getElementById('modal-content');
  const modalClose = document.getElementById('modal-close');

  function showModal(m){
    modal.hidden = false;
    modalContent.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true">
        <img src="${m.poster_url}" alt="${escapeHtml(m.title)}" onerror="this.onerror=null;this.src='/static/images/default_poster.png'"/>
        <div class="modal-content-right">
          <h2 style="margin-top:0">${escapeHtml(m.title)} <small style="color:var(--muted)">(${m.year||''})</small></h2>
          <p style="color:var(--muted)">Director: ${escapeHtml(m.director||'N/A')}</p>
          <p style="color:var(--muted)">Producer: ${escapeHtml(m.producer||'N/A')}</p>
          <h5 style="margin-top:12px">Cast</h5>
          <p style="color:var(--muted)">${escapeHtml(m.cast||'Not available')}</p>
          <div style="margin-top:18px">
            <a href="/movie/${m.id}" class="glass-btn">Open Page</a>
            <button id="modal-close-btn" class="glass-btn">Close</button>
          </div>
        </div>
      </div>
    `;
    // close handlers
    document.getElementById('modal-close-btn').onclick = closeModal;
    modalClose.onclick = closeModal;
    modal.onclick = (e) => { if(e.target === modal) closeModal(); };
  }

  function closeModal(){
    modal.hidden = true;
    modalContent.innerHTML = '';
  }

  function escapeHtml(text){
    if(!text) return '';
    return text.replace(/[&<>"']/g, (s) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  }

  // import status poll (if admin started import)
  const importStatusPoll = async () => {
    try{
      const r = await fetch('/admin/import_status');
      if(!r.ok) return;
      const s = await r.json();
      // show a console log and small toast via flash area if running
      if(s.running){
        console.log(`TMDB import running: ${s.inserted} inserted`);
      }
    }catch(e){}
  };
  setInterval(importStatusPoll, 5000);

});
