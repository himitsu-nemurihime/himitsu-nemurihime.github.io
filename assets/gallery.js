/* 出荷済みの絵のギャラリー
   🚨2026-09-01：index.html から切り出した。index.html と gallery.html が共有する。
   🚨2026-09-02：**ルピナスのサイトの三姉妹ギャラリーと同じものを使う**ようにした
     （中身を2本持つとズレるため。作りは gallery_core.py と同じ考え方）。
     ・キャラの色と並び順は**目録（gallery.json）の chars から読む**（決め打ちしない）
     ・目録の場所は #grid の data-src。無ければ data/gallery.json
   ・data-limit 属性が付いていたら、その枚数だけ出す（トップの「最近の絵」用）
   ・付いていなければ全件（一覧ページ用）
   ・NSFWゾーン(ntabs/ngrid)は要素がある時だけ組み立てる */
(function(){
  var DATA=null, view=[], cur=0, ORDER=[];

  var g0=document.getElementById('grid');
  var SRC=(g0 && g0.getAttribute('data-src')) || 'data/gallery.json';

  fetch(SRC,{cache:'no-cache'})
    .then(function(r){ if(!r.ok) throw 0; return r.json(); })
    .then(function(d){ DATA=d; ORDER=Object.keys(d.chars||{}); render(); })
    .catch(function(){
      var e=document.getElementById('gempty');
      if(e){ e.hidden=false; e.textContent='絵の一覧を読み込めませんでした。'; }
    });

  function shortOf(k){ return (DATA.chars[k]||{}).short || k; }
  function colorOf(k){ return (DATA.chars[k]||{}).color || 'currentColor'; }

  /* limit ＝ 0 なら全件、1以上ならその枚数だけ（新しい順に先頭から） */
  function build(zone, tabsEl, gridEl, emptyEl, limit){
    if(!gridEl) return 0;
    var all=DATA.items.filter(function(i){ return zone==='nsfw' ? i.nsfw : !i.nsfw; });
    var have=ORDER.filter(function(k){ return all.some(function(i){return i.char===k;}); });
    tabsEl.innerHTML='';
    var defs=[{k:'all',label:'ぜんぶ',n:all.length}].concat(have.map(function(k){
      return {k:k,label:shortOf(k),n:all.filter(function(i){return i.char===k;}).length};
    }));
    defs.forEach(function(d,idx){
      var li=document.createElement('li');
      var b=document.createElement('button');
      b.className='tab'; b.type='button'; b.setAttribute('role','tab');
      b.setAttribute('aria-selected', idx===0 ? 'true':'false');
      b.innerHTML=esc(d.label)+'<span class="n">'+d.n+'</span>';
      b.addEventListener('click',function(){
        Array.prototype.forEach.call(tabsEl.querySelectorAll('.tab'),function(t){
          t.setAttribute('aria-selected','false'); });
        b.setAttribute('aria-selected','true');
        paint(all, d.k, gridEl, emptyEl, limit);
        // 枚数が変わるとページの高さが変わって、いま見ていた場所からずれる。
        // タブの位置に戻してあげる。
        var top=tabsEl.getBoundingClientRect().top;
        if(top<0 || top>innerHeight*.5) tabsEl.scrollIntoView({block:'center'});
      });
      li.appendChild(b); tabsEl.appendChild(li);
    });
    paint(all,'all',gridEl,emptyEl,limit);
    return all.length;
  }

  function paint(all, key, gridEl, emptyEl, limit){
    var list = key==='all' ? all : all.filter(function(i){return i.char===key;});
    if(limit>0) list=list.slice(0,limit);
    gridEl.innerHTML='';
    if(emptyEl) emptyEl.hidden = list.length>0;
    list.forEach(function(it,idx){
      var b=document.createElement('button');
      b.className='card'; b.type='button';
      b.style.setProperty('--c',colorOf(it.char));
      b.style.animationDelay=Math.min(idx,14)*40+'ms';
      var img=document.createElement('img');
      img.src=it.thumb; img.alt=it.title; img.loading='lazy';
      img.width=it.w; img.height=it.h;
      var meta=document.createElement('span');
      meta.className='meta';
      meta.innerHTML='<span class="who">'+esc(shortOf(it.char))+'</span><br>'+esc(it.title);
      b.appendChild(img); b.appendChild(meta);
      b.addEventListener('click',function(){ view=list; open(idx); });
      gridEl.appendChild(b);
    });
  }

  function esc(s){ return String(s).replace(/[&<>"]/g,function(m){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]; }); }

  /* 🚨2026-09-01：ページによって出す枚数と持っている要素が違うので、
     「無い要素は触らない」「limit があればその枚数だけ」に直した。
     ・index.html（トップ）＝ #grid に data-limit="12" を付けて最近の12枚だけ／NSFWゾーンあり
     ・gallery.html（一覧）＝ limit なしで全件／NSFWゾーンは無い */
  function el(id){ return document.getElementById(id); }

  function render(){
    var grid=el('grid');
    var lim=grid ? parseInt(grid.getAttribute('data-limit')||'0',10) : 0;
    var n=build('sfw', el('tabs'), grid, el('gempty'), lim);
    var c=el('gcount');
    if(c) c.textContent = lim && n>lim
      ? 'いまは '+n+' 枚。ここには新しい '+lim+' 枚を出しています。'
      : 'いまは '+n+' 枚。';

    // NSFWゾーンはトップ（夜のほう）にしかない
    if(el('ntabs')) build('nsfw', el('ntabs'), el('ngrid'), el('nempty'), 0);

    var hn=el('heldnote');
    if(hn && DATA.held>0) hn.textContent='（いまのところ '+DATA.held+' 枚）';
    var up=el('updated');
    if(up && DATA.updated) up.textContent='さいごの絵：'+DATA.updated;
  }

  /* 大きく見る */
  var v=document.getElementById('viewer'), vi=document.getElementById('vimg'),
      vc=document.getElementById('vcap');
  function open(i){
    cur=(i+view.length)%view.length;
    var it=view[cur];
    vi.src=it.src; vi.alt=it.title;
    vc.textContent=shortOf(it.char)+'　'+it.title+'　（'+it.date+'）';
    v.hidden=false; document.body.style.overflow='hidden';
  }
  function close(){ v.hidden=true; vi.src=''; document.body.style.overflow=''; }
  document.getElementById('vx').addEventListener('click',close);
  document.getElementById('vprev').addEventListener('click',function(e){e.stopPropagation();open(cur-1);});
  document.getElementById('vnext').addEventListener('click',function(e){e.stopPropagation();open(cur+1);});
  v.addEventListener('click',function(e){ if(e.target===v||e.target.tagName==='DIV') close(); });
  addEventListener('keydown',function(e){
    if(v.hidden) return;
    if(e.key==='Escape') close();
    else if(e.key==='ArrowLeft') open(cur-1);
    else if(e.key==='ArrowRight') open(cur+1);
  });
})();

