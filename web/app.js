/* ==========================================================================
   سیستم حسابداری Mental — نسخهٔ صنف باتری‌فروشان
   ========================================================================== */

/* ------------------------- تاریخ شمسی (جاوااسکریپت) ----------------------- */
const JDate = (() => {
  const gDays = [0,31,59,90,120,151,181,212,243,273,304,334];
  function g2j(gy, gm, gd){
    const gy2 = gm > 2 ? gy + 1 : gy;
    let days = 355666 + (365*gy) + Math.floor((gy2+3)/4) - Math.floor((gy2+99)/100)
             + Math.floor((gy2+399)/400) + gd + gDays[gm-1];
    let jy = -1595 + 33*Math.floor(days/12053); days %= 12053;
    jy += 4*Math.floor(days/1461); days %= 1461;
    if(days > 365){ jy += Math.floor((days-1)/365); days = (days-1)%365; }
    let jm, jd;
    if(days < 186){ jm = 1 + Math.floor(days/31); jd = 1 + days%31; }
    else { jm = 7 + Math.floor((days-186)/30); jd = 1 + (days-186)%30; }
    return [jy, jm, jd];
  }
  function j2g(jy, jm, jd){
    jy += 1595;
    let days = -355668 + 365*jy + Math.floor(jy/33)*8 + Math.floor(((jy%33)+3)/4)
             + jd + (jm < 7 ? (jm-1)*31 : (jm-7)*30 + 186);
    let gy = 400*Math.floor(days/146097); days %= 146097;
    if(days > 36524){ days--; gy += 100*Math.floor(days/36524); days %= 36524;
      if(days >= 365) days++; }
    gy += 4*Math.floor(days/1461); days %= 1461;
    if(days > 365){ gy += Math.floor((days-1)/365); days = (days-1)%365; }
    let gd = days + 1;
    const leap = (gy%4===0 && gy%100!==0) || gy%400===0;
    const md = [0,31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
    let gm = 1;
    for(gm=1; gm<=12; gm++){ if(gd <= md[gm]) break; gd -= md[gm]; }
    return [gy, gm, gd];
  }
  const pad = n => String(n).padStart(2,'0');
  return {
    today(){ const d = new Date(); const j = g2j(d.getFullYear(), d.getMonth()+1, d.getDate());
      return `${j[0]}/${pad(j[1])}/${pad(j[2])}`; },
    toJalali(dateObj){ const j = g2j(dateObj.getFullYear(), dateObj.getMonth()+1, dateObj.getDate());
      return `${j[0]}/${pad(j[1])}/${pad(j[2])}`; },
    toDate(str){
      const p = (str||'').replace(/-/g,'/').split('/').map(x=>parseInt(x,10));
      if(p.length!==3 || p.some(isNaN)) return new Date();
      const g = j2g(p[0], p[1], p[2]); return new Date(g[0], g[1]-1, g[2]);
    },
    isValid(str){ const p=(str||'').replace(/-/g,'/').split('/').map(x=>parseInt(x,10));
      return p.length===3 && !p.some(isNaN) && p[1]>=1 && p[1]<=12 && p[2]>=1 && p[2]<=31; }
  };
})();

const MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];

/* --------------------------------- ابزارها -------------------------------- */
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nf = new Intl.NumberFormat('fa-IR');
const money = n => nf.format(Math.round(Number(n)||0));
const qtyf = n => { const v = Number(n)||0; return nf.format(Number.isInteger(v)? v : Math.round(v*1000)/1000); };

/* نام و نشان برنامه — یکجا عوض می‌شود و همه‌جا همین می‌آید */
const BRAND = 'سیستم حسابداری Mental';
const BRAND_SHORT = 'Mental';

/* آیکون‌های SVG (طبق چک‌لیست اسکیل: هیچ ایموجی‌ای به‌عنوان آیکون استفاده نمی‌شود) */
const ic = (name, cls) => `<svg class="${cls||'ico'}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;

/* ------------------------------ صداهای برنامه ---------------------------- */
/* بدون هیچ فایل صوتی: چند نُت کوتاه با Web Audio ساخته می‌شود. به این ترتیب
   حجم برنامه بالا نمی‌رود و فایل بیرونی هم لازم نیست. کاربر می‌تواند
   با کلید کنار «تم» صدای برنامه را خاموش کند (انتخابش ذخیره می‌شود). */
const Sfx = {
  KEY: 'saba-sound',
  enabled: true,
  ctx: null,

  init(){
    try{
      if(localStorage.getItem(this.KEY) === 'off') this.enabled = false;
    }catch(e){ /* حالت خصوصی مرورگر */ }
    this.reflect();
    /* مرورگر تا نخستین برخورد کاربر اجازهٔ پخش صدا نمی‌دهد */
    const unlock = () => { if(this.enabled) this.ensure(); };
    ['pointerdown', 'keydown'].forEach(ev =>
      window.addEventListener(ev, unlock, {once:true, passive:true}));
  },

  ensure(){
    try{
      const AC = window.AudioContext || window.webkitAudioContext;
      if(!AC) return null;
      if(!this.ctx) this.ctx = new AC();
      if(this.ctx.state === 'suspended') this.ctx.resume();
      return this.ctx;
    }catch(e){ return null; }
  },

  /* یک نُت با پاکت نرم (بدون «تق» تیز) */
  tone(freq, start, dur, type, gain){
    const ctx = this.ensure();
    if(!ctx || ctx.state !== 'running') return;
    const t0 = ctx.currentTime + start;
    const osc = ctx.createOscillator(), amp = ctx.createGain();
    osc.type = type || 'sine';
    osc.frequency.setValueAtTime(freq, t0);
    amp.gain.setValueAtTime(0.0001, t0);
    amp.gain.exponentialRampToValueAtTime(gain || .045, t0 + 0.014);
    amp.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(amp); amp.connect(ctx.destination);
    osc.start(t0); osc.stop(t0 + dur + 0.03);
  },

  play(name){
    if(!this.enabled) return;
    switch(name){
      case 'save':                                   // کار انجام شد
        this.tone(587, 0, .10); this.tone(784, .085, .12);
        this.tone(1046, .17, .22); break;
      case 'ok':
        this.tone(660, 0, .11); this.tone(880, .085, .17); break;
      case 'error':                                  // بازخورد ناموفق
        this.tone(220, 0, .17, 'triangle', .05);
        this.tone(165, .12, .22, 'triangle', .045); break;
      case 'pop':  this.tone(520, 0, .07, 'sine', .035); break;
      case 'click': this.tone(880, 0, .035, 'square', .012); break;
    }
  },

  toggle(){
    this.enabled = !this.enabled;
    try{ localStorage.setItem(this.KEY, this.enabled ? 'on' : 'off'); }catch(e){}
    this.reflect();
    if(this.enabled){ this.ensure(); this.play('ok'); }
    return this.enabled;
  },

  reflect(){
    const btn = $('#soundToggle'), use = $('#soundIconUse'), label = $('#soundLabel');
    if(btn){
      btn.classList.toggle('muted', !this.enabled);
      btn.setAttribute('aria-pressed', String(this.enabled));
      btn.title = this.enabled ? 'خاموش کردن صداهای برنامه' : 'روشن کردن صداهای برنامه';
    }
    if(use) use.setAttribute('href', this.enabled ? '#i-sound-on' : '#i-sound-off');
    if(label) label.textContent = this.enabled ? 'صدا روشن' : 'صدا خاموش';
  },
};

/* --------------------------- انیمیشن‌های برنامه --------------------------- */
/* اگر سیستم‌عامل «کاهش حرکت» را روشن کرده باشد، انیمیشن‌ها خاموش می‌شوند؛
   کاربر می‌تواند از کلید پایین صفحه آن‌ها را روشن کند. انتخابش ذخیره می‌شود. */
const Motion = {
  KEY: 'saba-motion',
  forced: false,                       // true = کاربر خودش روشن کرده است

  init(){
    try{ this.forced = localStorage.getItem(this.KEY) === 'on'; }catch(e){}
    this.apply();
  },

  apply(){
    const root = document.documentElement;
    if(this.forced) root.setAttribute('data-motion', 'on');
    else root.removeAttribute('data-motion');
    const btn = $('#animToggle'), label = $('#animLabel');
    const reduced = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(btn){
      btn.classList.toggle('muted', !this.forced);
      btn.setAttribute('aria-pressed', String(this.forced));
      btn.title = this.forced ? 'خاموش کردن انیمیشن‌ها'
        : (reduced ? 'سیستم شما انیمیشن را خاموش کرده؛ برای روشن کردن بزنید'
                   : 'روشن کردن انیمیشن‌ها');
    }
    if(label) label.textContent = this.forced ? 'انیمیشن روشن' : 'انیمیشن';
  },

  toggle(){
    this.forced = !this.forced;
    try{ localStorage.setItem(this.KEY, this.forced ? 'on' : 'off'); }catch(e){}
    this.apply();
    return this.forced;
  },
};

function toast(msg, type){
  const kind = type === 'ok' ? 'ok' : type === 'error' ? 'error' : 'info';
  const icon = kind === 'ok' ? 'check' : kind === 'error' ? 'warning' : 'info';
  /* برای پیام‌هایی که صدای خودشان را جدا می‌زنند: نوع silent */
  if(type !== 'silent'){
    if(kind === 'ok') Sfx.play('save');
    else if(kind === 'error') Sfx.play('error');
    else Sfx.play('pop');
  }
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  t.innerHTML = ic(icon) + '<span class="truncate">' + esc(msg) + '</span>';
  $('#toastRoot').appendChild(t);
  setTimeout(() => {
    t.classList.add('leaving');
    setTimeout(() => t.remove(), 220);
  }, 3600);
}

/* حالت بارگذاری: اسکلتون به‌جای صفحهٔ خالی */
function skeleton(kind){
  if(kind === 'stats')
    return '<div class="skel-stats">' + Array.from({length: 6}).map(() =>
      '<div class="skel-stat"><div class="skel" style="width:45%;margin-bottom:14px"></div>' +
      '<div class="skel" style="width:70%;height:22px"></div></div>').join('') + '</div>';
  return '<div class="card skel-card">' + Array.from({length: 7}).map(() =>
    '<div class="skel-row"><span class="skel"></span><span class="skel"></span>' +
    '<span class="skel"></span></div>').join('') + '</div>';
}

/* حالت خالی: پیام راهنما + اقدام (طبق راهنمای UX) */
function emptyState(title, hint, actionLabel, actionJs){
  return '<div class="empty">' +
    '<span class="empty-icon">' + ic('empty') + '</span>' +
    '<span class="empty-title">' + esc(title) + '</span>' +
    (hint ? '<span class="empty-hint">' + esc(hint) + '</span>' : '') +
    (actionLabel ? '<button type="button" class="btn primary small" onclick="' + actionJs +
      '">' + ic('plus') + esc(actionLabel) + '</button>' : '') +
  '</div>';
}

/* تلاش دوباره فقط روی خطای شبکه؛ خطای HTTP بلافاصله برگردانده می‌شود */
async function fetchRetry(url, init, tries){
  tries = tries || 3;
  let last;
  for(let i = 0; i < tries; i++){
    try { return await fetch(url, init); }
    catch(e){
      last = e;
      if(i < tries - 1) await new Promise(z => setTimeout(z, 400 * (i + 1)));
    }
  }
  const err = new Error('ارتباط با سرور برقرار نشد');
  err.network = true;
  err.cause = last;
  throw err;
}

async function api(path, opts){
  opts = opts || {};
  const init = { method: opts.method || 'GET', headers: {},
                 credentials:'same-origin', cache:'no-store' };
  if(opts.body !== undefined){
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetchRetry('/api/' + path, init);
  let data;
  try { data = await res.json(); } catch(e){ throw new Error('پاسخ نامعتبر از سرور'); }
  if(res.status === 401){ App.showLogin(); throw new Error(data.error || 'ابتدا وارد سامانه شوید'); }
  if(res.status === 403 && data.license_required){
    App.showActivate(data.license);
    throw new Error(data.error || 'برنامه فعال نشده است');
  }
  if(res.status === 402){
    const e = new Error(data.error || 'این بخش نیازمند نسخهٔ پرمیوم است');
    e.premium = true;
    throw e;
  }
  if(!res.ok || data.ok === false) throw new Error(data.error || 'خطای نامشخص');
  return data.data;
}
const apiTry = async (p,o) => {
  try { return await api(p,o); }
  catch(e){
    // خطای شبکه یعنی سرویس محلی در دسترس نیست؛ صفحهٔ عیب‌یابی نشان بده
    if(e.network) App.connectionError('درخواست به سرویس محلی نرسید.');
    else toast(e.message,'error');
    return null;
  }
};

/* ------------------------------- منوی برنامه ------------------------------ */
/* perm: کلید دسترسی لازم (کوچک‌ترین سطح دسترسی قابل واگذاری به کاربر)
   premium: کلید قابلیت پرمیوم؛ بدون آن بخش قفل نشان داده می‌شود
   admin: فقط برای کاربر با نقش مدیر */
const NAV = [
  { group:'عملیات روزانه', perm:'invoices', items:[
    {id:'dashboard', title:'داشبورد', icon:'dashboard'},
    {id:'invoices-sale', title:'فاکتور فروش', icon:'invoice-sale'},
    {id:'invoices-proforma', title:'پیش‌فاکتور', icon:'proforma'},
    {id:'invoices-sale_return', title:'برگشت از فروش', icon:'sale-return'},
    {id:'invoices-purchase', title:'فاکتور خرید', icon:'purchase'},
    {id:'invoices-purchase_return', title:'برگشت از خرید', icon:'purchase-return'},
  ]},
  { group:'صنف باتری', perm:'battery', items:[
    {id:'battery-serials', title:'سریال و گارانتی باتری', icon:'battery'},
    {id:'battery-scrap', title:'خرید باتری فرسوده', icon:'scrap'},
    {id:'battery-scrap-sales', title:'فروش ضایعات', icon:'scrap-sale'},
  ]},
  { group:'انبارداری', perm:'inventory', items:[
    {id:'inventory', title:'موجودی کالا', icon:'inventory'},
    {id:'inventory-cardex', title:'گردش کالا (کاردکس)', icon:'cardex'},
    {id:'inventory-transfer', title:'انتقال بین انبار', icon:'transfer', premium:'multi_warehouse'},
    {id:'inventory-adjust', title:'اصلاح موجودی', icon:'adjust', premium:'multi_warehouse'},
  ]},
  { group:'حسابداری', perm:'accounting', items:[
    {id:'accounting-receipts', title:'دریافت و پرداخت', icon:'money-in'},
    {id:'accounting-journal', title:'اسناد حسابداری', icon:'journal'},
    {id:'accounting-trial', title:'تراز آزمایشی', icon:'trial', premium:'adv_reports'},
    {id:'accounting-pl', title:'سود و زیان', icon:'profit', premium:'adv_reports'},
    {id:'accounting-bs', title:'ترازنامه', icon:'balance', premium:'adv_reports'},
  ]},
  { group:'چک و اسناد', perm:'cheques', items:[
    {id:'cheques-receivable', title:'چک‌های دریافتنی', icon:'cheque-in'},
    {id:'cheques-payable', title:'چک‌های پرداختنی', icon:'cheque-out'},
    {id:'cheques-due', title:'سررسید چک‌ها', icon:'cheque-due'},
  ]},
  { group:'تعاریف پایه', perm:'defs', items:[
    {id:'parties', title:'اشخاص و طرف حساب', icon:'parties'},
    {id:'products', title:'کالاها', icon:'products'},
    {id:'groups', title:'گروه کالا', icon:'groups'},
    {id:'units', title:'واحد سنجش', icon:'units'},
    {id:'warehouses', title:'انبارها', icon:'warehouses', premium:'multi_warehouse'},
  ]},
  { group:'گزارشات', perm:'reports', items:[
    {id:'reports-sales', title:'گزارش فروش و خرید', icon:'report-sales'},
    {id:'reports-products', title:'پرفروش‌ترین کالاها', icon:'report-products'},
    {id:'reports-debtors', title:'اشخاص بدهکار', icon:'report-debtors'},
    {id:'reports-inventory', title:'ارزش موجودی انبار', icon:'report-inventory'},
  ]},
  { group:'سیستم', perm:'system', items:[
    {id:'system-users', title:'کاربران', icon:'users', premium:'more_users'},
    {id:'system-activity', title:'گردش فعالیت کاربران', icon:'activity', premium:'audit'},
    {id:'system-audit', title:'گزارش اصلاح و حذف', icon:'audit', premium:'audit'},
    {id:'system-notes', title:'یادداشت و یادآور', icon:'notes'},
    {id:'system-backup', title:'پشتیبان‌گیری', icon:'backup', premium:'backup'},
    {id:'system-settings', title:'تنظیمات', icon:'settings'},
    {id:'account', title:'حساب کاربری و لایسنس', icon:'user'},
    {id:'license', title:'وضعیت لایسنس', icon:'lock'},
  ]},
];

/* برچسب فارسی قابلیت‌های پرمیوم (هم‌راستا با app/licensing.py) */
const FEATURE_LABELS = {
  multi_warehouse:'چند انبار، انتقال و اصلاح موجودی چندانباری',
  more_users:'بیش از یک کاربر فعال',
  backup:'پشتیبان‌گیری، بازیابی و خروجی اکسل (CSV)',
  adv_reports:'گزارش‌های مالی پیشرفته (تراز آزمایشی، سود و زیان، ترازنامه)',
  audit:'ردیابی حذف و اصلاح و گردش فعالیت کاربران',
};

/* برچسب فارسی دسترسی‌های کاربر (هم‌راستا با PERM_KEYS در app/server.py) */
const PERM_LABELS = {
  invoices:'فاکتور فروش و خرید', battery:'صنف باتری (سریال، گارانتی، ضایعات)',
  inventory:'انبارداری', accounting:'حسابداری', cheques:'چک و اسناد',
  defs:'تعاریف پایه (اشخاص، کالا، انبار)', reports:'گزارشات',
};

/* ------------------------------ مؤلفه‌های عمومی ---------------------------- */
function table(cols, rows, opts){
  opts = opts || {};
  if(!rows || !rows.length)
    return emptyState(opts.emptyTitle || 'موردی برای نمایش نیست', opts.empty || '',
                      opts.emptyAction, opts.emptyActionJs);
  const head = cols.map(c =>
    `<th scope="col" class="${c.cls||''}" style="${c.style||''}">${c.title}</th>`).join('');
  const body = rows.map(r => '<tr>' + cols.map(c => {
    const v = c.render ? c.render(r) : esc(r[c.key] == null ? '' : r[c.key]);
    return `<td class="${c.cls||''}" style="${c.style||''}">${v}</td>`;
  }).join('') + '</tr>').join('');
  return `<div class="table-wrap ${opts.compact?'compact':''}"><table><thead><tr>${head}</tr>` +
         `</thead><tbody>${body}</tbody></table></div>`;
}

function modal(title, bodyHtml, footHtml, wide){
  Sfx.play('pop');
  const root = $('#modalRoot');
  root.innerHTML = `<div class="modal-back" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
     <div class="modal ${wide?'wide':''}">
       <div class="modal-head">
         <h2 id="modalTitle">${title}</h2>
         <button type="button" class="icon-btn plain" aria-label="بستن" onclick="App.closeModal()">${ic('close')}</button>
       </div>
       <div class="modal-body">${bodyHtml}</div>
       <div class="modal-foot">${footHtml||''}</div>
     </div></div>`;
  App._lastFocus = document.activeElement;
  App._trapFocus();
  const first = root.querySelector('input:not([type=hidden]),select,textarea,button');
  if(first) setTimeout(() => first.focus(), 40);
}
function closeModal(){
  if(App._stopConnWatch) App._stopConnWatch();   // صفحهٔ عیب‌یابی بسته شد
  if($('#modalRoot').innerHTML) Sfx.play('click');
  $('#modalRoot').innerHTML = '';
  if(App._lastFocus && App._lastFocus.focus && document.contains(App._lastFocus))
    App._lastFocus.focus();
}

function field(f, v){
  v = v == null ? (f.value == null ? '' : f.value) : v;
  const id = 'f_' + f.name;
  const lbl = `<label for="${id}">${esc(f.label)}` +
    (f.required ? '<span class="req" aria-hidden="true"> *</span>' : '') + '</label>';
  const err = `<p class="field-error" id="${id}_err"></p>`;
  if(f.type === 'select'){
    const opts = (f.options||[]).map(o => {
      const val = o.value !== undefined ? o.value : o;
      const l = o.label !== undefined ? o.label : o;
      return `<option value="${esc(val)}" ${String(val)===String(v)?'selected':''}>${esc(l)}</option>`;
    }).join('');
    return `<div class="field"><label for="${id}">${esc(f.label)}</label>
      <select id="${id}" ${f.required?'required':''}>${opts}</select>${err}</div>`;
  }
  if(f.type === 'textarea')
    return `<div class="field">${lbl}<textarea id="${id}" rows="2" ` +
      `${f.required?'required':''}>${esc(v)}</textarea>${err}</div>`;
  if(f.type === 'date')
    return `<div class="field">${lbl}<div class="date-row">
      <input id="${id}" value="${esc(v||JDate.today())}" inputmode="numeric"
        placeholder="۱۴۰۵/۰۷/۲۲" ${f.required?'required':''}>
      <button type="button" class="btn small" aria-label="امروز"
        onclick="document.getElementById('${id}').value=JDate.today()">${ic('calendar')}</button>
      </div>${err}</div>`;
  return `<div class="field">${lbl}<input id="${id}" type="${f.type||'text'}" value="${esc(v)}" ` +
    `${f.step?`step="${f.step}"`:''} ${f.required?'required':''} ` +
    `${f.placeholder?`placeholder="${esc(f.placeholder)}"`:''}>${err}</div>`;
}
/* ردیف‌های «برچسب/مقدار» که در کارت‌های وضعیت زیاد به کار می‌روند */
function rowsOf(list){
  return list.map(r =>
    `<div class="row"><span class="muted small">${esc(r[0])}</span>
       <b>${r[1]}</b></div>`).join('');
}

const fieldVal = n => {
  const e = document.getElementById('f_' + n) || document.getElementById(n);
  return e ? e.value : '';
};
const fieldNum = n => Number(fieldVal(n)) || 0;

function modalForm(title, fields, values, onSaveHtml, opts){
  opts = opts || {};
  const grid = opts.grid || 'c2';
  const body = `<div class="form-grid ${grid}">` +
    fields.map(f => field(f, values?.[f.name])).join('') + '</div>';
  modal(title, body, onSaveHtml ||
    `<button class="btn primary" onclick="${opts.onSave}">${ic('save')}ذخیره</button>
     <button class="btn" onclick="App.closeModal()">انصراف</button>`, opts.wide);
}

/* ================================ برنامه ================================= */
const App = {
  meta:null, route:'dashboard', cache:{parties:[], products:[], warehouses:[]},

  /* ------------------------------ تم روشن/تیره ----------------------------- */
  /* انتخاب کاربر در مرورگر ذخیره می‌شود؛ بار اول از تنظیم سیستم می‌آید. */
  THEME_KEY: 'saba-theme',

  theme(){ return document.documentElement.getAttribute('data-theme') || 'light'; },

  applyTheme(theme, save){
    const dark = theme === 'dark';
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const cs = document.querySelector('meta[name="color-scheme"]');
    if(cs) cs.setAttribute('content', dark ? 'dark light' : 'light dark');
    const tc = document.querySelector('meta[name="theme-color"]');
    if(tc) tc.setAttribute('content', dark ? '#0B1220' : '#1E3A5F');
    const use = $('#themeIconUse');
    if(use) use.setAttribute('href', dark ? '#i-sun' : '#i-moon');
    const label = $('#themeLabel');
    if(label) label.textContent = dark ? 'تم روشن' : 'تم تیره';
    const btn = $('#themeToggle');
    if(btn) btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    if(save){
      try{ localStorage.setItem(this.THEME_KEY, dark ? 'dark' : 'light'); }catch(e){}
    }
  },

  initTheme(){
    let saved = '';
    try{ saved = localStorage.getItem(this.THEME_KEY) || ''; }catch(e){ /* حالت خصوصی */ }
    const system = (window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    this.applyTheme(saved || system, false);
  },

  toggleTheme(){
    const next = this.theme() === 'dark' ? 'light' : 'dark';
    this.applyTheme(next, true);
    toast(next === 'dark' ? 'تم تیره فعال شد' : 'تم روشن فعال شد', 'info');
  },

  /* روشن/خاموش کردن صداهای برنامه (پیام‌ها، پنجره‌ها، کارهای انجام‌شده) */
  toggleSound(){
    const on = Sfx.toggle();
    toast(on ? 'صدای برنامه روشن شد' : 'صدای برنامه خاموش شد', 'silent');
  },

  /* روشن/خاموش کردن انیمیشن‌ها (وقتی سیستم‌عامل کاهش حرکت را روشن کرده) */
  toggleMotion(){
    const on = Motion.toggle();
    toast(on ? 'انیمیشن‌های برنامه روشن شد'
             : 'انیمیشن‌های برنامه خاموش شد', 'silent');
    if(on){
      const c = $('#content');
      if(c){ c.classList.remove('replay'); void c.offsetWidth; c.classList.add('replay'); }
    }
  },

  async boot(){
    this.initTheme();
    Sfx.init();
    Motion.init();
    this.initShell();
    const ping = await this.pingServer();
    if(!ping){
      this.showLogin();
      this.connectionError('سرویس محلی به درخواست /api/ping پاسخ نداد.');
      return;
    }
    // پیش از هر کار دیگری، وضعیت لایسنس بررسی می‌شود
    if(!(await this.checkLicense())) return;
    let me = null;
    try {
      me = await (await fetchRetry('/api/meta',
        {credentials:'same-origin', cache:'no-store'})).json();
    } catch(e){ /* پایین رسیدگی می‌شود */ }
    if(me && me.ok){ this.meta = me.data; this.start(); }
    else this.showLogin();
  },

  /* چند بار تلاش می‌کند تا سرویس محلی تازه‌راه‌افتاده پاسخ دهد */
  async pingServer(){
    for(let i = 0; i < 5; i++){
      try{
        const r = await fetch('/api/ping?_=' + Date.now(), {cache:'no-store'});
        if(r.ok) return await r.json();
      }catch(e){ /* تلاش دوباره */ }
      await new Promise(z => setTimeout(z, 500));
    }
    return null;
  },

  /* صفحهٔ عیب‌یابی وقتی سرویس محلی در دسترس نیست */
  connectionError(detail){
    const url = location.origin;
    modal('ارتباط با سرویس برنامه برقرار نشد',
      `<div class="hint bad"><span class="ico">${ic('warning')}</span>
         <span>صفحه در مرورگر باز شد ولی سرویس داخلی برنامه پاسخ نمی‌دهد.
         این معمولاً یعنی سرویس بسته شده یا یک نمونهٔ قدیمی از برنامه مانده است.</span></div>
       <div class="stack mt4">
         <div class="row"><span class="muted small">نشانی سرویس:</span>
           <code class="mono">${esc(url)}</code></div>
         ${detail ? `<div class="row"><span class="muted small">جزئیات:</span>
           <span class="small">${esc(detail)}</span></div>` : ''}
         <div class="hint"><span class="ico">${ic('info')}</span>
           <span>اگر تکرار شد: در «Task Manager» همهٔ نمونه‌های
           <b>Mental accounting.exe</b> را ببندید و برنامه را یک‌بار دیگر اجرا کنید.
           فایل گزارش در <code class="mono">data\\app.log</code> کنار فایل اجرایی است.</span></div>
       </div>`,
      `<button class="btn primary" onclick="App.closeModal();App.retryConnection()">
         ${ic('refresh')}تلاش دوباره</button>
       <button class="btn" onclick="location.reload()">بارگذاری مجدد صفحه</button>`);
    this._startConnWatch();
  },

  /* تا وقتی این صفحه باز است، هر چند ثانیه سرویس را می‌پاید و به‌محض
     برگشتن سرویس، خودکار وصل می‌شود تا کاربر در حالت مرده گیر نکند. */
  _startConnWatch(){
    this._stopConnWatch();
    this._connWatch = setInterval(async () => {
      if(this._connBusy) return;
      this._connBusy = true;
      const ping = await this.pingServer();
      this._connBusy = false;
      if(ping){ this._stopConnWatch(); this.retryConnection(); }
    }, 4000);
  },

  _stopConnWatch(){
    if(this._connWatch){ clearInterval(this._connWatch); this._connWatch = null; }
    this._connBusy = false;
  },

  async retryConnection(){
    this._stopConnWatch();
    const ping = await this.pingServer();
    if(!ping){ this.connectionError('هنوز پاسخی از سرویس دریافت نشد.'); return; }
    try {
      const me = await (await fetchRetry('/api/meta',
        {credentials:'same-origin', cache:'no-store'})).json();
      if(me && me.ok){
        this.meta = me.data;
        closeModal();                       // صفحهٔ عیب‌یابی بسته شود
        toast('ارتباط با سرویس برقرار شد','ok');
        this.start();
        return;
      }
    } catch(e){ /* پایین */ }
    closeModal();
    this.showLogin();
  },

  /* رویدادهای پوسته: منوی موبایل، پالت جستجو، کلیدهای میانبر، ESC */
  initShell(){
    const toggle = $('#navToggle'), scrim = $('#scrim');
    const closeNav = () => {
      $('#sidebar').classList.remove('open');
      scrim.classList.add('hidden');
      toggle.setAttribute('aria-expanded','false');
    };
    toggle.addEventListener('click', () => {
      const open = $('#sidebar').classList.toggle('open');
      scrim.classList.toggle('hidden', !open);
      toggle.setAttribute('aria-expanded', String(open));
    });
    scrim.addEventListener('click', closeNav);
    this._closeNav = closeNav;

    $('#loginForm').addEventListener('submit', e => { e.preventDefault(); this.doLogin(); });
    $('#searchTrigger').addEventListener('click', () => this.openPalette());

    const pin = $('#paletteInput');
    pin.addEventListener('input', () => this.paletteSearch(pin.value.trim()));
    pin.addEventListener('keydown', e => {
      if(e.key === 'ArrowDown'){ e.preventDefault(); this.paletteMove(1); }
      else if(e.key === 'ArrowUp'){ e.preventDefault(); this.paletteMove(-1); }
      else if(e.key === 'Enter'){ e.preventDefault(); this.paletteChoose(); }
    });
    $('#paletteBack').addEventListener('click', e => {
      if(e.target === $('#paletteBack')) this.closePalette();
    });

    document.addEventListener('keydown', e => {
      if(e.key === 'Escape'){
        if(!$('#paletteBack').classList.contains('hidden')) this.closePalette();
        else if($('#modalRoot').innerHTML) this.closeModal();
        else if($('#sidebar').classList.contains('open')) this._closeNav();
      }
      if((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k'){
        e.preventDefault(); this.openPalette();
      }
    });
  },

  /* نگهداشتن فوکوس داخل مودال (دسترسی‌پذیری keyboard) */
  _trapFocus(){
    const root = $('#modalRoot');
    if(!root || root._trap) return;
    root._trap = true;
    root.addEventListener('keydown', e => {
      if(e.key !== 'Tab') return;
      const nodes = root.querySelectorAll(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),' +
        'textarea:not([disabled]),[tabindex]:not([tabindex="-1"])');
      if(!nodes.length) return;
      const first = nodes[0], last = nodes[nodes.length - 1];
      if(e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
      else if(!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
    });
  },

  showLogin(){
    $('#activateScreen').classList.add('hidden');
    $('#loginScreen').classList.remove('hidden');
    $('#app').classList.add('hidden');

  },

  /* --------------------------- فعال‌سازی برنامه --------------------------- */
  async checkLicense(){
    let info = null;
    try{
      const r = await fetchRetry('/api/license',
        {credentials:'same-origin', cache:'no-store'});
      const d = await r.json();
      info = d && d.data;
    }catch(e){ return true; }        // اگر خوانده نشد، جریان عادی ادامه می‌یابد
    if(info && info.required && !info.valid){ this.showActivate(info); return false; }
    return true;
  },

  showActivate(info){
    info = info || {};
    this._license = info;
    $('#loginScreen').classList.add('hidden');
    $('#app').classList.add('hidden');
    $('#activateScreen').classList.remove('hidden');
    const code = $('#machineCode');
    if(code) code.textContent = info.machine_code || '—';
    const note = $('#activateNote');
    if(note) note.textContent = info.message || 'برای ادامه، لایسنس این رایانه را وارد کنید.';
    const state = $('#activateState');
    if(state){
      state.textContent = info.installed
        ? 'لایسنس فعلی معتبر نیست — لایسنس درست را وارد کنید'
        : 'برنامه فعال نشده است';
    }
    const err = $('#activateError');
    if(err){ err.textContent = info.installed ? (info.message||'') : '';
             err.classList.toggle('show', !!info.installed); }
    const manual = $('#manualBox');
    if(manual) manual.open = !!info.installed || !this._cloudConfigured;
    // وضعیت فعال‌سازی آنلاین و شروع پایش خودکار
    this.loadCloud().then(c => { this.renderCloud(c); });
  },

  /* ------------------- فعال‌سازی آنلاین (سرور لایسنس/بات بله) ------------------ */
  CLOUD_LABELS: {pending:'در انتظار تأیید فروشنده', active:'تأیید شد',
                 denied:'رد شد', revoked:'لغو شده', expired:'منقضی',
                 none:'ثبت نشده'},

  async loadCloud(){
    try{
      const r = await fetchRetry('/api/license/cloud',
        {cache:'no-store', credentials:'same-origin'});
      const d = await r.json();
      if(d && d.ok){ this._cloud = d.data; return d.data; }
    }catch(e){ /* سرویس محلی پاسخ نداد */ }
    return null;
  },

  renderCloud(data){
    const c = ((data || this._cloud) || {}).cloud || {};
    this._cloudConfigured = !!c.configured;
    const box = $('#cloudBox');
    if(!box) return;
    if(!c.configured){
      box.classList.add('hidden');
      const manual = $('#manualBox');
      if(manual) manual.open = true;
      return;
    }
    box.classList.remove('hidden');
    const status = c.status || '';
    const badge = $('#cloudBadge');
    if(badge){
      badge.textContent = this.CLOUD_LABELS[status] || 'آماده';
      badge.className = 'badge ' + (status === 'active' ? 'ok'
        : (status === 'pending' ? 'warn' : ((status && status !== 'none') ? 'bad' : 'neutral')));
    }
    const hint = $('#cloudHint');
    if(hint){
      hint.textContent = c.message || (status === 'pending'
        ? 'درخواست شما به فروشنده رسیده است؛ به‌محض تأیید، همین صفحه خودکار فعال می‌شود.'
        : 'با فرستادن درخواست، فروشنده در پیام‌رسان بله آن را تأیید می‌کند و مجوز همین رایانه صادر می‌شود.');
    }
    const form = $('#cloudForm');
    const btn = $('#cloudReqBtn');
    const pending = (status === 'pending');
    if(form) form.style.display = pending ? 'none' : '';
    if(btn){
      btn.innerHTML = ic('check') +
        (pending ? 'ارسال دوبارهٔ درخواست' : 'ارسال درخواست فعال‌سازی به فروشنده');
      btn.disabled = false;
    }
    const note = $('#cloudNote');
    if(note){
      const bits = [];
      if(c.server) bits.push('سرور: ' + c.server);
      if(c.checked_at) bits.push('آخرین بررسی: ' + c.checked_at);
      if(c.error) bits.push('خطای آخر: ' + c.error);
      note.textContent = bits.join('  |  ');
    }
    if(pending) this.startCloudWatch(); else this.stopCloudWatch();
  },

  startCloudWatch(){
    this.stopCloudWatch();
    this._cloudTimer = setInterval(() => this.cloudPoll(false), 5000);
  },

  stopCloudWatch(){
    if(this._cloudTimer){ clearInterval(this._cloudTimer); this._cloudTimer = null; }
  },

  async cloudRequest(){
    const name = ($('#cloudName') || {}).value || '';
    const phone = ($('#cloudPhone') || {}).value || '';
    const d = await apiTry('license/cloud/request',
      {method:'POST', body:{name:name.trim(), phone:phone.trim()}});
    if(d === null) return;
    this._cloud = {cloud: d.cloud, license: d.license};
    this.renderCloud({cloud: d.cloud});
    this.startCloudWatch();
    toast('درخواست فعال‌سازی برای فروشنده فرستاده شد','ok');
  },

  async cloudPoll(manual){
    const d = await apiTry('license/cloud/poll', {method:'POST'});
    if(d === null) return;
    this._cloud = {cloud: d.cloud, license: d.license};
    this.renderCloud({cloud: d.cloud});
    if(d.license && d.license.valid){
      this.stopCloudWatch();
      toast('برنامه فعال شد','ok');
      setTimeout(() => location.reload(), 700);
      return;
    }
    if(manual){
      if(d.checked) toast(d.message || 'هنوز تأیید نشده است', 'info');
      else toast(d.message || 'ارتباط با سرور لایسنس برقرار نشد', 'error');
    }
  },

  copyMachine(){
    const text = ($('#machineCode') || {}).textContent || '';
    if(!text || text === '—'){ toast('کدی برای کپی نیست','error'); return; }
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(
        () => toast('کد رایانه کپی شد','ok'),
        () => toast('کپی نشد؛ کد را دستی یادداشت کنید','error'));
    }else{
      toast('کد را دستی یادداشت کنید: ' + text,'info');
    }
  },

  readLicenseFile(ev){
    const f = ev && ev.target && ev.target.files && ev.target.files[0];
    if(!f) return;
    const r = new FileReader();
    r.onload = () => { $('#licenseKey').value = String(r.result || '').trim(); };
    r.readAsText(f);
  },

  async doActivate(){
    const err = $('#activateError');
    err.classList.remove('show');
    const key = ($('#licenseKey').value || '').trim();
    if(!key){ err.textContent = 'متن لایسنس را وارد کنید'; err.classList.add('show'); return; }
    try{
      const res = await fetchRetry('/api/license/activate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        cache:'no-store', credentials:'same-origin',
        body: JSON.stringify({key})});
      const d = await res.json();
      if(!d.ok){ err.textContent = d.error || 'فعال‌سازی ناموفق بود'; err.classList.add('show'); return; }
      toast('برنامه فعال شد','ok');
      location.reload();
    }catch(e){
      if(e.network){ this.connectionError('درخواست فعال‌سازی به سرویس محلی نرسید.'); return; }
      err.textContent = e.message || 'ارتباط با سرور برقرار نشد';
      err.classList.add('show');
    }
  },

  /* --------------------------- قابلیت‌های پرمیوم --------------------------- */
  features(){
    const lic = (this.meta && this.meta.license) || {};
    return lic.features || [];
  },

  isAdmin(){ return !!(this.meta && this.meta.user && this.meta.user.role === 'admin'); },

  hasFeature(key){ return this.features().indexOf(key) !== -1; },

  showPremiumRequired(msg){
    modal('این بخش در نسخهٔ پرمیوم باز است',
      `<div class="hint warn"><span class="ico">${ic('lock')}</span>
         <span>${esc(msg || 'برای استفاده از این قابلیت، لایسنس پرمیوم لازم است.')}</span></div>
       <p class="muted small">${this.isAdmin()
          ? 'برای فعال‌سازی نسخهٔ پرمیوم، کد این رایانه را به فروشنده بفرستید و لایسنس دریافتی را در صفحهٔ «لایسنس و فعال‌سازی» وارد کنید.'
          : 'برای فعال‌سازی نسخهٔ پرمیوم با مدیر سیستم تماس بگیرید.'}</p>`,
      (this.isAdmin()
        ? `<button class="btn primary" onclick="App.closeModal();App.navigate('license')">
             نمایش صفحهٔ لایسنس</button>`
        : '') +
      `<button class="btn" onclick="App.closeModal()">بستن</button>`);
  },

  premiumBlock(item){
    const label = FEATURE_LABELS[item.premium] || 'این قابلیت';
    return this.dwrap(item.title, '',
      `<div class="card premium-box">
         <div class="mark">${ic('lock')}</div>
         <h2>${esc(item.title)} در نسخهٔ پرمیوم فعال است</h2>
         <p><b>${esc(label)}</b> یکی از قابلیت‌های نسخهٔ پرمیوم برنامه است.
            با فعال‌سازی نسخهٔ پرمیوم، این بخش و بقیهٔ قابلیت‌های حرفه‌ای باز می‌شود.</p>
         ${this.isAdmin()
           ? `<div class="row" style="justify-content:center">
                <button class="btn primary" onclick="App.navigate('license')">
                  ${ic('lock')}وضعیت و فعال‌سازی لایسنس</button>
              </div>`
           : `<p class="muted small">برای فعال‌سازی نسخهٔ پرمیوم با مدیر سیستم تماس بگیرید.</p>`}
       </div>`);
  },

  async doLogin(){
    const err = $('#loginError');
    err.classList.remove('show');
    try{
      const res = await fetchRetry('/api/login', {
        method:'POST', headers:{'Content-Type':'application/json'}, cache:'no-store',
        body: JSON.stringify({username: $('#loginUser').value,
                              password: $('#loginPass').value})});
      const d = await res.json();
      if(!d.ok){ err.textContent = d.error; err.classList.add('show'); return; }
      this.meta = await api('meta');
      this.start();
    }catch(e){
      if(e.network){ this.connectionError('درخواست ورود به سرویس محلی نرسید.'); return; }
      err.textContent = e.message || 'ارتباط با سرور برقرار نشد';
      err.classList.add('show');
    }
  },

  async logout(){
    await fetch('/api/logout', {method:'POST'});
    location.reload();
  },

  async start(){
    $('#loginScreen').classList.add('hidden');
    $('#activateScreen').classList.add('hidden');
    $('#app').classList.remove('hidden');
    this.renderNav();
    const s = this.meta.settings;
    $('#topCompany').textContent = s.company_name || 'فروشگاه باتری';
    $('#topDate').textContent = `${this.meta.weekday} ${this.meta.today}`;
    $('#sideUser').textContent = this.meta.user.full_name || this.meta.user.username || '—';
    const lic = this.meta.license || {};
    $('#sideRole').textContent =
      (this.meta.user.role === 'admin' ? 'مدیر سیستم' : 'کاربر') +
      (lic.mode === 'admin' ? ' — نسخهٔ مدیر' :
        (lic.valid && lic.edition === 'premium' ? ' — پرمیوم' : ''));
    document.title = (s.company_name ? s.company_name + ' — ' : '') + BRAND;
    if(lic.expires && typeof lic.days_left === 'number' && lic.days_left <= 30){
      setTimeout(() => toast(lic.days_left <= 0
        ? 'لایسنس برنامه منقضی شده است'
        : 'لایسنس تا ' + lic.days_left + ' روز دیگر منقضی می‌شود', 'info'), 900);
    }
    await this.refreshCache();
    this.navigate(this.route || 'dashboard');
    this.checkReminders();
  },

  async refreshCache(){
    const [p, pr, w] = await Promise.all([
      api('parties'), api('products'), api('warehouses')]);
    this.cache.parties = p||[]; this.cache.products = pr||[]; this.cache.warehouses = w||[];
  },

  /* دسترسی‌های کاربر جاری؛ برای نقش مدیر همهٔ بخش‌ها باز است */
  myPerms(){
    if(this.isAdmin()) return null;              // null یعنی همه
    const u = (this.meta && this.meta.user) || {};
    const list = (u.perms && u.perms.length)
      ? u.perms : Object.keys(PERM_LABELS);      // خالی = سازگاری با نصب‌های قدیمی
    return new Set(list);
  },

  canSee(item, groupPerm){
    if(item && item.id === 'dashboard') return true;   // داشبورد همیشه هست
    if(this.isAdmin()) return true;
    const perms = this.myPerms();
    if(!perms) return true;
    if(groupPerm === 'system') return false;     // بخش سیستم فقط برای مدیر
    return perms.has(groupPerm);
  },

  navItems(){
    return NAV.map(g => Object.assign({}, g,
      {items: g.items.filter(i => this.canSee(i, g.perm))}))
      .filter(g => g.items.length);
  },

  findItem(id){
    for(const g of NAV) for(const i of g.items) if(i.id === id) return i;
    return null;
  },

  renderNav(){
    const groups = this.navItems();
    $('#nav').innerHTML = groups.map(g => `<div class="nav-group">
      <div class="nav-group-title">${g.group}</div>
      ${g.items.map(i => `<button type="button" class="nav-item" data-id="${i.id}">
        <span class="ico">${ic(i.icon)}</span>
        <span class="label">${i.title}</span>
        ${(i.premium && !this.hasFeature(i.premium))
            ? `<span class="lock-chip">${ic('lock')}پرمیوم</span>` : ''}
      </button>`).join('')}
    </div>`).join('');
    $$('#nav .nav-item').forEach(el => el.addEventListener('click', () => {
      Sfx.play('click');
      this.navigate(el.dataset.id);
    }));
  },

  async navigate(id){
    this.route = id;
    $$('#nav .nav-item').forEach(el => {
      const on = el.dataset.id === id;
      el.classList.toggle('active', on);
      if(on) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current');
    });
    if(this._closeNav) this._closeNav();
    const c = $('#content');
    const item = this.findItem(id);
    if(item && item.premium && !this.hasFeature(item.premium)){
      c.innerHTML = this.premiumBlock(item);
      c.scrollTop = 0;
      return;
    }
    c.innerHTML = (id === 'dashboard') ? skeleton('stats') : skeleton('table');
    c.scrollTop = 0;
    try {
      const key = 'v_' + id.replace(/-/g, '');
      if(id.startsWith('invoices-')) await this.viewInvoice(id.replace('invoices-',''));
      else if(this[key]) await this[key]();
      else c.innerHTML = emptyState('صفحه یافت نشد', 'این بخش در دسترس نیست.');
    } catch(e){
      if(e.network) this.connectionError('درخواست به سرویس محلی نرسید.');
      else c.innerHTML = emptyState('خطا در بارگذاری', e.message);
    }
  },

  async checkReminders(){
    try{
      const notes = await api('notes');
      const today = this.meta.today;
      const due = (notes||[]).filter(n => !n.done && n.remind_at && n.remind_at <= today);
      if(due.length) toast(`${due.length} یادآور سررسیدشده دارید`);
      const chq = await api('reports/cheque-due?days=10');
      if(chq && chq.length) toast(`${chq.length} چک نزدیک سررسید است`);
    }catch(e){}
  },

  /* ---------------------------- پالت جستجو (Ctrl+K) --------------------- */
  openPalette(){
    if($('#app').classList.contains('hidden')) return;
    const back = $('#paletteBack');
    back.classList.remove('hidden');
    const inp = $('#paletteInput');
    inp.value = '';
    inp.setAttribute('aria-expanded','true');
    this._paletteItems = [];
    this._paletteIndex = -1;
    $('#paletteList').innerHTML =
      '<div class="palette-empty">نام کالا، شخص یا شمارهٔ فاکتور را بنویسید</div>';
    inp.focus();
  },

  closePalette(){
    $('#paletteBack').classList.add('hidden');
    $('#paletteInput').setAttribute('aria-expanded','false');
  },

  async paletteSearch(q){
    const list = $('#paletteList');
    if(!q){
      this._paletteItems = [];
      list.innerHTML = '<div class="palette-empty">نام کالا، شخص یا شمارهٔ فاکتور را بنویسید</div>';
      return;
    }
    let d;
    try { d = await api('search?q=' + encodeURIComponent(q)); } catch(e){ return; }
    const items = [];
    (d.parties||[]).forEach(p => items.push({icon:'parties', label:p.name,
      sub:p.mobile||'', kind:'شخص', route:'parties'}));
    (d.products||[]).forEach(p => items.push({icon:'products', label:p.name,
      sub:[p.brand,p.amperage].filter(Boolean).join(' '), kind:'کالا', route:'products'}));
    (d.invoices||[]).forEach(p => items.push({icon:'invoice-sale', label:p.number,
      sub:`${this.kindName(p.kind)} — ${money(p.total)}`, kind:'فاکتور',
      route:'invoices-' + p.kind}));
    this._paletteItems = items;
    this._paletteIndex = items.length ? 0 : -1;
    if(!items.length){
      list.innerHTML = '<div class="palette-empty">نتیجه‌ای یافت نشد</div>';
      return;
    }
    list.innerHTML = items.map((it, i) => `<button type="button" class="palette-item"
        role="option" aria-selected="${i===0}" data-i="${i}">
        ${ic(it.icon)}
        <span class="truncate">${esc(it.label)}</span>
        <span class="kind truncate">${esc(it.sub || it.kind)}</span>
      </button>`).join('');
    $$('#paletteList .palette-item').forEach(el => {
      el.addEventListener('click', () => {
        this._paletteIndex = Number(el.dataset.i);
        this.paletteChoose();
      });
    });
  },

  paletteMove(step){
    if(!this._paletteItems || !this._paletteItems.length) return;
    const n = this._paletteItems.length;
    this._paletteIndex = (this._paletteIndex + step + n) % n;
    $$('#paletteList .palette-item').forEach((el, i) =>
      el.setAttribute('aria-selected', String(i === this._paletteIndex)));
    const cur = $('#paletteList .palette-item[aria-selected="true"]');
    if(cur) cur.scrollIntoView({block:'nearest'});
  },

  paletteChoose(){
    const it = (this._paletteItems||[])[this._paletteIndex];
    if(!it) return;
    this.closePalette();
    this.navigate(it.route);
  },

  closeModal, toast,

  // ------------------------------------------------------------------ داشبورد
  async v_dashboard(){
    const d = await api('dashboard');
    const cur = this.cur();
    const stat = (label, value, cls, icon, sub) =>
      `<div class="stat">
         <div class="lbl">${ic(icon)}${label}</div>
         <div class="val ${cls||''}">${value}</div>
         ${sub?`<div class="sub">${sub}</div>`:''}
       </div>`;
    let html = `<div class="page-head">
      <div>
        <h1 class="page-title">داشبورد مدیریت</h1>
        <div class="page-sub">نگاه کلی به فروش، انبار و مطالبات</div>
      </div>
      <div class="page-actions">
        <button class="btn primary" onclick="App.quickInvoice('sale')">${ic('invoice-sale')}فاکتور فروش جدید</button>
        <button class="btn" onclick="App.quickScrap()">${ic('scrap')}ثبت باتری فرسوده</button>
      </div></div>`;
    html += `<div class="grid cols-3">
      ${stat('فروش امروز', money(d.sales_today)+' '+cur, 'ok', 'money-in')}
      ${stat('فروش این ماه', money(d.sales_month)+' '+cur, 'info', 'profit')}
      ${stat('فروش سال جاری', money(d.sales_year)+' '+cur, 'info', 'report-sales')}
      ${stat('خرید این ماه', money(d.purchase_month)+' '+cur, null, 'purchase')}
      ${stat('موجودی صندوق و بانک', money(d.cash)+' '+cur, 'ok', 'money-in')}
      ${stat('مطالبات (بدهکاران)', money(d.receivable)+' '+cur, 'bad', 'report-debtors', nf.format(d.debtor_count)+' شخص بدهکار')}
    </div>`;
    html += `<div class="grid cols-4 mt4">
      ${stat('ارزش موجودی انبار', money(d.stock_value)+' '+cur, null, 'inventory')}
      ${stat('تعداد کالا', nf.format(d.product_count), null, 'products')}
      ${stat('تعداد اشخاص', nf.format(d.party_count), null, 'parties')}
      ${stat('موجودی ضایعات', nf.format(Math.round(d.scrap.weight))+' کیلوگرم', null, 'scrap', money(d.scrap.value)+' '+cur)}
    </div>`;

    html += `<div class="grid cols-2 mt4">
      <div class="card"><div class="card-head"><h2 class="card-title">${ic('invoice-sale')}آخرین فاکتورها</h2>
        <button class="btn small" onclick="App.navigate('invoices-sale')">مشاهده همه</button></div>
        ${table([
          {title:'شماره', key:'number'},
          {title:'نوع', render: r => `<span class="badge info">${esc(this.kindName(r.kind))}</span>`},
          {title:'تاریخ', key:'date'},
          {title:'مبلغ', render: r => `<span class="num">${money(r.total)}</span>`},
        ], d.recent)}</div>
      <div class="card"><div class="card-head"><h2 class="card-title">${ic('cheque-due')}چک‌های نزدیک سررسید</h2></div>
        ${table([
          {title:'شماره', key:'number'},
          {title:'طرف حساب', render: r => esc(r.party_name||'—')},
          {title:'سررسید', key:'due_date'},
          {title:'روز مانده', render: r => r.days_left < 0 ? `<span class="badge bad">گذشته</span>` : `<span class="badge warn">${nf.format(r.days_left)}</span>`},
          {title:'مبلغ', render: r => `<span class="num">${money(r.amount)}</span>`},
        ], d.cheque_due, {empty:'چک نزدیک سررسیدی وجود ندارد'})}</div>
    </div>`;

    html += `<div class="card"><div class="card-head"><h2 class="card-title">${ic('warning')}کالاهای نیازمند سفارش (زیر حد سفارش)</h2></div>
      ${table([
        {title:'کد', key:'code'},
        {title:'نام کالا', key:'name'},
        {title:'برند', key:'brand'},
        {title:'موجودی', render: r => `<span class="badge bad">${qtyf(r.stock)}</span>`},
        {title:'حد سفارش', render: r => qtyf(r.reorder_level)},
      ], d.low_stock, {empty:'موجودی همه کالاها مناسب است'})}</div>`;
    $('#content').innerHTML = html;
  },

  cur(){ return (this.meta && this.meta.settings.currency) || 'ریال'; },
  kindName(k){ return (this.meta && this.meta.kinds[k]) || k; },
  dwrap(title, actions, inner){ return `<div class="page-head">
    <h1 class="page-title">${title}</h1>
    <div class="page-actions">${actions||''}</div></div>${inner}`; },
};

/* ============================ ادامهٔ صفحه‌ها =============================== */
Object.assign(App, {

  optParties(sel){ return (this.cache.parties||[]).map(p =>
    `<option value="${p.id}" ${String(p.id)===String(sel)?'selected':''}>${esc(p.name)}${p.mobile?(' — '+esc(p.mobile)):''}</option>`).join(''); },
  optProducts(sel){ return (this.cache.products||[]).map(p =>
    `<option value="${p.id}" ${String(p.id)===String(sel)?'selected':''}>${esc(p.name)}${p.amperage?(' ('+esc(p.amperage)+')'):''}</option>`).join(''); },
  optWarehouses(sel){ return (this.meta.warehouses||[]).map(w =>
    `<option value="${w.id}" ${String(w.id)===String(sel)?'selected':''}>${esc(w.name)}</option>`).join(''); },
  optAccounts(sel){ return (this.meta.accounts||[]).map(a =>
    `<option value="${esc(a.name)}" ${a.name===sel?'selected':''}>${esc(a.name)}</option>`).join(''); },
  optEmpty(){ return '<option value="">— انتخاب کنید —</option>'; },

  /* ------------------------------- اشخاص -------------------------------- */
  async v_parties(){
    const q = this._pq || '';
    const rows = await api('parties?q=' + encodeURIComponent(q));
    const cols = [
      {title:'کد', key:'code'},
      {title:'نام شخص', render:r=>`<b>${esc(r.name)}</b>`},
      {title:'نوع', render:r=>`<span class="badge neutral">${r.party_type==='customer'?'مشتری':r.party_type==='supplier'?'فروشنده':'مشتری و فروشنده'}</span>`},
      {title:'تلفن', render:r=>esc(r.mobile||r.phone||'—')},
      {title:'کد ملی', render:r=>esc(r.national_id||'—')},
      {title:'مانده حساب', render:r=>r.balance>0?`<span class="badge bad">بدهکار ${money(r.balance)}</span>`:r.balance<0?`<span class="badge ok">بستانکار ${money(-r.balance)}</span>`:'<span class="badge neutral">تسویه</span>'},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.partyLedger(${r.id})">ریز حساب</button>
        <button class="btn small" onclick="App.editParty(${r.id})">ویرایش</button>
        <button class="btn small danger" onclick="App.delParty(${r.id})">حذف</button>`},
    ];
    $('#content').innerHTML = this.dwrap('اشخاص و طرف حساب‌ها',
      `<button class="btn primary" onclick="App.editParty()">+ شخص جدید</button>`,
      `<div class="card"><div class="inline" style="margin-bottom:12px">
        <div class="field"><input id="pq" value="${esc(q)}" placeholder="جستجوی نام، تلفن یا کد..." onkeydown="if(event.key==='Enter'){App._pq=this.value;App.navigate('parties')}"></div>
        <button class="btn" onclick="App._pq=document.getElementById('pq').value;App.navigate('parties')">جستجو</button></div>
        ${table(cols, rows)}</div>`);
  },

  editParty(id){
    const p = id ? (this.cache.parties||[]).find(x=>x.id===id) : null;
    const fields = [
      {name:'name', label:'نام شخص / شرکت', value:p?p.name:''},
      {name:'code', label:'کد اختصاصی', value:p?p.code:''},
      {name:'party_type', label:'نوع طرف حساب', type:'select', value:p?p.party_type:'customer',
       options:[{value:'customer',label:'مشتری'},{value:'supplier',label:'فروشنده'},{value:'both',label:'مشتری و فروشنده'}]},
      {name:'national_id', label:'کد ملی / شناسه ملی', value:p?p.national_id:''},
      {name:'economic_code', label:'کد اقتصادی', value:p?p.economic_code:''},
      {name:'mobile', label:'همراه', value:p?p.mobile:''},
      {name:'phone', label:'تلفن ثابت', value:p?p.phone:''},
      {name:'city', label:'شهر', value:p?p.city:''},
      {name:'opening_balance', label:'مانده اول دوره (+ بدهکار / - بستانکار)', type:'number', value:p?p.opening_balance:0},
      {name:'credit_limit', label:'سقف اعتبار', type:'number', value:p?p.credit_limit:0},
      {name:'address', label:'نشانی', type:'textarea', value:p?p.address:''},
      {name:'note', label:'یادداشت', type:'textarea', value:p?p.note:''},
    ];
    modalForm(id?'ویرایش شخص':'ثبت شخص جدید', fields, null,
      `<button class="btn primary" onclick="App.saveParty(${id||0})">ذخیره</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`, {wide:false});
  },

  async saveParty(id){
    const d = {name:fieldVal('name'), code:fieldVal('code'), party_type:fieldVal('party_type'),
      national_id:fieldVal('national_id'), economic_code:fieldVal('economic_code'),
      mobile:fieldVal('mobile'), phone:fieldVal('phone'), city:fieldVal('city'),
      opening_balance:fieldNum('opening_balance'), credit_limit:fieldNum('credit_limit'),
      address:fieldVal('address'), note:fieldVal('note')};
    if(!d.name){ toast('نام شخص الزامی است','error'); return; }
    const r = await apiTry('parties' + (id?('/'+id):''), {method:id?'PUT':'POST', body:d});
    if(r !== null){ this.closeModal(); toast('اطلاعات ذخیره شد','ok'); await this.refreshCache(); this.navigate(this.route); }
  },

  async delParty(id){
    if(!confirm('این شخص حذف شود؟')) return;
    await apiTry('parties/'+id, {method:'DELETE'});
    await this.refreshCache(); this.navigate('parties');
  },

  async partyLedger(id){
    const d = await api('parties/'+id+'/ledger');
    const cols = [
      {title:'تاریخ', key:'date'},
      {title:'شرح', key:'description'},
      {title:'بدهکار', render:r=>r.debit?`<span class="num">${money(r.debit)}</span>`:''},
      {title:'بستانکار', render:r=>r.credit?`<span class="num">${money(r.credit)}</span>`:''},
      {title:'مانده', render:r=>`<span class="num">${money(r.balance)}</span>`},
    ];
    modal('ریز حساب: ' + esc(d.party.name),
      `<div class="hint" style="margin-bottom:12px">مانده نهایی: <b>${d.balance>0?'بدهکار':'بستانکار'} ${money(Math.abs(d.balance))} ${this.cur()}</b></div>`
      + table(cols, d.ledger),
      `<button class="btn" onclick="App.closeModal()">بستن</button>`, true);
  },

  /* -------------------------------- کالاها ------------------------------- */
  async v_products(){
    const q = this._prodq || '';
    const rows = await api('products?q=' + encodeURIComponent(q));
    const cols = [
      {title:'کد', key:'code'},
      {title:'نام کالا', render:r=>`<b>${esc(r.name)}</b>${r.brand?`<div class="small muted">${esc(r.brand)} ${esc(r.amperage||'')} ${esc(r.battery_type||'')}</div>`:''}`},
      {title:'گروه', render:r=>esc(r.group_name||'—')},
      {title:'واحد', render:r=>esc(r.unit_name||'—')},
      {title:'قیمت خرید', render:r=>`<span class="num">${money(r.purchase_price)}</span>`},
      {title:'قیمت فروش', render:r=>`<span class="num">${money(r.sale_price)}</span>`},
      {title:'گارانتی', render:r=>r.warranty_months?`<span class="badge ok">${nf.format(r.warranty_months)} ماه</span>`:'—'},
      {title:'موجودی', render:r=>`<span class="badge ${r.stock>0?'blue':'red'}">${qtyf(r.stock)}</span>`},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.editProduct(${r.id})">ویرایش</button>
        <button class="btn small danger" onclick="App.delProduct(${r.id})">حذف</button>`},
    ];
    $('#content').innerHTML = this.dwrap('کالاها و باتری‌ها',
      `<button class="btn" onclick="App.navigate('groups')">گروه کالا</button>
       <button class="btn" onclick="App.navigate('units')">واحد سنجش</button>
       <button class="btn primary" onclick="App.editProduct()">+ کالای جدید</button>`,
      `<div class="card"><div class="inline" style="margin-bottom:12px">
        <div class="field"><input id="prodq" value="${esc(q)}" placeholder="جستجوی نام، کد، بارکد یا برند..." onkeydown="if(event.key==='Enter'){App._prodq=this.value;App.navigate('products')}"></div>
        <button class="btn" onclick="App._prodq=document.getElementById('prodq').value;App.navigate('products')">جستجو</button></div>
        ${table(cols, rows)}</div>`);
  },

  editProduct(id){
    const p = id ? (this.cache.products||[]).find(x=>x.id===id) : null;
    const gopts = this.optEmpty() + (this.meta.groups||[]).map(g=>`<option value="${g.id}" ${p&&p.group_id===g.id?'selected':''}>${esc(g.name)}</option>`).join('');
    const uopts = this.optEmpty() + (this.meta.units||[]).map(u=>`<option value="${u.id}" ${p&&p.unit_id===u.id?'selected':''}>${esc(u.name)}</option>`).join('');
    const fields = [
      {name:'name', label:'نام کالا', value:p?p.name:''},
      {name:'code', label:'کد کالا', value:p?p.code:''},
      {name:'barcode', label:'بارکد', value:p?p.barcode:''},
      {name:'group_id', label:'گروه کالا', type:'select', options:[]},
      {name:'unit_id', label:'واحد سنجش', type:'select', options:[]},
      {name:'brand', label:'برند (مثلاً وارتا، سپاهان)', value:p?p.brand:''},
      {name:'amperage', label:'آمپر (مثلاً ۶۶، ۷۰، ۱۰۰)', value:p?p.amperage:''},
      {name:'battery_type', label:'نوع باتری (خودرو، یو‌پی‌اس، موتور)', value:p?p.battery_type:''},
      {name:'capacity_ah', label:'ظرفیت (آمپرساعت)', type:'number', value:p?p.capacity_ah:0},
      {name:'warranty_months', label:'مدت گارانتی (ماه)', type:'number', value:p?p.warranty_months:0},
      {name:'purchase_price', label:'قیمت خرید', type:'number', value:p?p.purchase_price:0},
      {name:'sale_price', label:'قیمت فروش (تک‌فروشی)', type:'number', value:p?p.sale_price:0},
      {name:'wholesale_price', label:'قیمت فروش عمده', type:'number', value:p?p.wholesale_price:0},
      {name:'reorder_level', label:'حد سفارش (آلارم موجودی)', type:'number', value:p?p.reorder_level:0},
      {name:'is_battery', label:'باتری است؟', type:'select', value:p?String(p.is_battery):'1', options:[{value:'1',label:'بله'},{value:'0',label:'خیر'}]},
      {name:'note', label:'یادداشت', type:'textarea', value:p?p.note:''},
    ];
    if(!id){
      fields.splice(15,0,
        {name:'opening_stock', label:'موجودی اول دوره', type:'number', value:0},
        {name:'opening_date', label:'تاریخ موجودی اول دوره', type:'date', value:this.meta.today});
    }
    modalForm(id?'ویرایش کالا':'ثبت کالای جدید', fields, null,
      `<button class="btn primary" onclick="App.saveProduct(${id||0})">ذخیره</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`);
    document.getElementById('f_group_id').innerHTML = gopts;
    document.getElementById('f_unit_id').innerHTML = uopts;
  },

  async saveProduct(id){
    const d = {name:fieldVal('name'), code:fieldVal('code'), barcode:fieldVal('barcode'),
      group_id:fieldVal('group_id')||null, unit_id:fieldVal('unit_id')||null,
      brand:fieldVal('brand'), amperage:fieldVal('amperage'), battery_type:fieldVal('battery_type'),
      capacity_ah:fieldNum('capacity_ah'), warranty_months:fieldNum('warranty_months'),
      purchase_price:fieldNum('purchase_price'), sale_price:fieldNum('sale_price'),
      wholesale_price:fieldNum('wholesale_price'), reorder_level:fieldNum('reorder_level'),
      is_battery:Number(fieldVal('is_battery')||1), note:fieldVal('note')};
    if(!id){ d.opening_stock = fieldNum('opening_stock'); d.opening_date = fieldVal('opening_date'); }
    if(!d.name){ toast('نام کالا الزامی است','error'); return; }
    const r = await apiTry('products' + (id?('/'+id):''), {method:id?'PUT':'POST', body:d});
    if(r !== null){ this.closeModal(); toast('کالا ذخیره شد','ok'); await this.refreshCache(); this.navigate('products'); }
  },

  async delProduct(id){
    if(!confirm('این کالا حذف/غیرفعال شود؟')) return;
    await apiTry('products/'+id, {method:'DELETE'});
    await this.refreshCache(); this.navigate('products');
  },

  async v_groups(){
    const rows = await api('groups');
    $('#content').innerHTML = this.dwrap('گروه کالا', `<button class="btn primary" onclick="App.addGroup()">+ گروه جدید</button>`,
      `<div class="card">${table([
        {title:'نام گروه', key:'name'},
        {title:'یادداشت', key:'note'},
        {title:'عملیات', render:r=>`<button class="btn small danger" onclick="App.delGroup(${r.id})">حذف</button>`},
      ], rows)}</div>`);
  },
  addGroup(){ modalForm('گروه کالای جدید', [{name:'name',label:'نام گروه'},{name:'note',label:'یادداشت'}], null,
    `<button class="btn primary" onclick="App.saveGroup()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`); },
  async saveGroup(){ const r = await apiTry('groups', {method:'POST', body:{name:fieldVal('name'), note:fieldVal('note')}});
    if(r!==null){ this.closeModal(); this.meta.groups = await api('groups'); this.navigate('groups'); } },
  async delGroup(id){ if(!confirm('حذف شود؟')) return; await apiTry('groups/'+id,{method:'DELETE'}); this.meta.groups = await api('groups'); this.navigate('groups'); },

  async v_units(){
    const rows = await api('units');
    $('#content').innerHTML = this.dwrap('واحد سنجش', `<button class="btn primary" onclick="App.addUnit()">+ واحد جدید</button>`,
      `<div class="card">${table([
        {title:'نام واحد', key:'name'},
        {title:'عملیات', render:r=>`<button class="btn small danger" onclick="App.delUnit(${r.id})">حذف</button>`},
      ], rows)}</div>`);
  },
  addUnit(){ modalForm('واحد سنجش جدید', [{name:'name',label:'نام واحد'}], null,
    `<button class="btn primary" onclick="App.saveUnit()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`); },
  async saveUnit(){ const r = await apiTry('units', {method:'POST', body:{name:fieldVal('name')}});
    if(r!==null){ this.closeModal(); this.meta.units = await api('units'); this.navigate('units'); } },
  async delUnit(id){ if(!confirm('حذف شود؟')) return; await apiTry('units/'+id,{method:'DELETE'}); this.meta.units = await api('units'); this.navigate('units'); },

  async v_warehouses(){
    const rows = await api('warehouses');
    $('#content').innerHTML = this.dwrap('انبارها', `<button class="btn primary" onclick="App.addWarehouse()">+ انبار جدید</button>`,
      `<div class="card">${table([
        {title:'نام انبار', key:'name'},
        {title:'موقعیت', key:'location'},
        {title:'پیش‌فرض', render:r=>r.is_default?'<span class="badge ok">بله</span>':'—'},
        {title:'عملیات', render:r=>`<button class="btn small danger" onclick="App.delWarehouse(${r.id})">حذف</button>`},
      ], rows)}</div>`);
  },
  addWarehouse(){ modalForm('انبار جدید', [{name:'name',label:'نام انبار'},{name:'location',label:'موقعیت'}], null,
    `<button class="btn primary" onclick="App.saveWarehouse()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`); },
  async saveWarehouse(){ const r = await apiTry('warehouses',{method:'POST', body:{name:fieldVal('name'), location:fieldVal('location')}});
    if(r!==null){ this.closeModal(); this.meta.warehouses = await api('warehouses'); this.navigate('warehouses'); } },
  async delWarehouse(id){ if(!confirm('حذف شود؟')) return; await apiTry('warehouses/'+id,{method:'DELETE'}); this.meta.warehouses = await api('warehouses'); this.navigate('warehouses'); },

  /* ------------------------------ فاکتورها ------------------------------ */
  async viewInvoice(kind){
    const q = this._invq || ''; const df = this._invf || ''; const dt = this._invt || '';
    const rows = await api(`invoices?kind=${kind}&q=${encodeURIComponent(q)}&from=${df}&to=${dt}`);
    const cols = [
      {title:'شماره', render:r=>`<b>${esc(r.number)}</b>`},
      {title:'تاریخ', key:'date'},
      {title:'طرف حساب', render:r=>esc(r.party_name||'—')},
      {title:'مبلغ کل', render:r=>`<span class="num">${money(r.total)}</span>`},
      {title:'تخفیف', render:r=>`<span class="num">${money(r.discount)}</span>`},
      {title:'پرداخت‌شده', render:r=>`<span class="num">${money(r.paid_cash+r.paid_card+r.paid_cheque)}</span>`},
      {title:'مانده', render:r=>{const p=r.total-r.paid_cash-r.paid_card-r.paid_cheque; return p>0?`<span class="badge bad">${money(p)}</span>`:'<span class="badge ok">تسویه</span>';}},
      {title:'وضعیت', render:r=>`<span class="badge ${r.status==='final'?'green':'gray'}">${r.status==='final'?'قطعیشده':'پیش‌نویس'}</span>`},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.invoiceEditor('${kind}',${r.id})">مشاهده/ویرایش</button>
        <button class="btn small danger" onclick="App.delInvoice(${r.id})">حذف</button>`},
    ];
    const total = rows.reduce((s,r)=>s+(r.total||0),0);
    $('#content').innerHTML = this.dwrap('لیست ' + this.kindName(kind),
      `<button class="btn primary" onclick="App.invoiceEditor('${kind}')">+ ${this.kindName(kind)} جدید</button>`,
      `<div class="card"><div class="inline" style="margin-bottom:12px">
        <div class="field"><input id="invq" value="${esc(q)}" placeholder="شماره فاکتور یا نام شخص..."></div>
        <div class="field"><input id="invf" value="${esc(df)}" placeholder="از تاریخ ۱۴۰۵/۰۱/۰۱"></div>
        <div class="field"><input id="invt" value="${esc(dt)}" placeholder="تا تاریخ"></div>
        <button class="btn" onclick="App.invFilter()">فیلتر</button></div>
        <div class="hint" style="margin-bottom:10px">جمع مبلغ فاکتورهای نمایش‌داده‌شده: <b>${money(total)} ${this.cur()}</b> — تعداد: ${nf.format(rows.length)}</div>
        ${table(cols, rows)}</div>`);
  },
  invFilter(){ this._invq=$('#invq').value; this._invf=$('#invf').value; this._invt=$('#invt').value;
    this.navigate(this.route); },

  blankItem(){ return {product_id:'', description:'', qty:1, unit_price:0, discount:0,
    tax_rate:Number(this.meta.settings.tax_rate||9), serial:'', warranty_months:0, cost_price:0}; },

  async invoiceEditor(kind, id){
    let inv=null; let items=[];
    if(id){ const d = await api('invoices/'+id); inv=d.invoice; items=d.items||[]; }
    else { items=[this.blankItem()]; }
    const number = inv ? inv.number : (await api('invoices/next_number?kind='+kind)).number;
    this._inv = {kind, id:id||0, items, products:this.cache.products||[]};
    const header = `<div class="form-grid c4">
      <div class="field"><label>شماره فاکتور</label><input id="iv_number" value="${esc(number)}"></div>
      ${field({name:'iv_date',label:'تاریخ',type:'date',value: inv?inv.date:this.meta.today})}
      <div class="field"><label>طرف حساب</label><select id="iv_party">${this.optEmpty()}${this.optParties(inv?inv.party_id:'')}</select></div>
      <div class="field"><label>انبار</label><select id="iv_wh">${this.optWarehouses(inv?inv.warehouse_id:'')}</select></div>
    </div>`;
    const itemHead = `<tr><th style="min-width:220px">کالا</th><th>توضیح</th><th>تعداد</th><th>قیمت واحد</th>
      <th>تخفیف</th><th>مالیات٪</th><th>جمع</th><th>سریال باتری</th><th>گارانتی(ماه)</th><th></th></tr>`;
    const rows = items.map((it,i)=>this.itemRow(it,i)).join('');
    const body = `${header}
      <div class="scroll-x" style="margin-top:14px"><table class="inv-items"><thead>${itemHead}</thead>
        <tbody id="iv_items">${rows}</tbody></table></div>
      <button class="btn small" style="margin-top:10px" onclick="App.invAddRow()">+ افزودن قلم</button>
      <div class="grid cols-2" style="margin-top:16px">
        <div>
          <div class="form-grid c2">
            <div class="field"><label>تخفیف کل فاکتور</label><input id="iv_disc" type="number" value="${inv?inv.discount:0}" oninput="App.invRecalc()"></div>
            <div class="field"><label>نرخ مالیات (٪)</label><input id="iv_taxrate" type="number" value="${inv?inv.tax_rate:(this.meta.settings.tax_rate||9)}"></div>
            <div class="field"><label>پرداخت نقدی</label><input id="iv_cash" type="number" value="${inv?inv.paid_cash:0}" oninput="App.invRecalc()"></div>
            <div class="field"><label>پرداخت کارت</label><input id="iv_card" type="number" value="${inv?inv.paid_card:0}" oninput="App.invRecalc()"></div>
            <div class="field"><label>پرداخت چک</label><input id="iv_cheque" type="number" value="${inv?inv.paid_cheque:0}" oninput="App.invRecalc()"></div>
            <div class="field"><label>وضعیت</label><select id="iv_status"><option value="final" ${!inv||inv.status==='final'?'selected':''}>قطعی</option><option value="draft" ${inv&&inv.status==='draft'?'selected':''}>پیش‌نویس</option></select></div>
          </div>
          <div class="field"><label>توضیحات</label><textarea id="iv_note" rows="2">${inv?esc(inv.note):''}</textarea></div>
        </div>
        <div class="totals" id="iv_totals"></div>
      </div>`;
    modal(`${id?'ویرایش':'ثبت'} ${this.kindName(kind)}`, body,
      `<button class="btn primary" onclick="App.invSave()">ذخیره فاکتور</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`, true);
    this.invRecalc();
  },

  itemRow(it,i){
    const opts = this.optEmpty() + (this.cache.products||[]).map(p=>
      `<option value="${p.id}" ${String(p.id)===String(it.product_id)?'selected':''}>${esc(p.name)}${p.amperage?(' ('+esc(p.amperage)+')'):''}</option>`).join('');
    return `<tr>
      <td><select class="iprod" data-i="${i}" onchange="App.invProductChange(this)">${opts}</select></td>
      <td><input class="idesc" data-i="${i}" value="${esc(it.description||'')}"></td>
      <td><input class="iqty" data-i="${i}" type="number" step="any" value="${it.qty}" oninput="App.invRecalc()"></td>
      <td><input class="iprice" data-i="${i}" type="number" value="${it.unit_price}" oninput="App.invRecalc()"></td>
      <td><input class="idisc" data-i="${i}" type="number" value="${it.discount}" oninput="App.invRecalc()"></td>
      <td><input class="itax" data-i="${i}" type="number" value="${it.tax_rate}" oninput="App.invRecalc()"></td>
      <td class="num iline">0</td>
      <td><input class="iserial" data-i="${i}" value="${esc(it.serial||'')}"></td>
      <td><input class="iwar" data-i="${i}" type="number" value="${it.warranty_months||0}"></td>
      <td><button class="btn small danger" onclick="App.invRemoveRow(${i})">✕</button></td>
    </tr>`;
  },

  invAddRow(){ this._inv.items.push(this.blankItem()); this.invReIndex(); },
  invRemoveRow(i){ if(this._inv.items.length<=1){ toast('حداقل یک قلم لازم است','error'); return; }
    this._inv.items.splice(i,1); this.invReIndex(); },
  invReIndex(){
    const tb = document.getElementById('iv_items');
    tb.innerHTML = this._inv.items.map((it,i)=>this.itemRow(it,i)).join('');
    this.invRecalc();
  },

  invProductChange(sel){
    const i = Number(sel.dataset.i); const p = (this.cache.products||[]).find(x=>String(x.id)===String(sel.value));
    if(!p) return;
    const row = sel.closest('tr');
    const isSale = ['sale','proforma','sale_return'].includes(this._inv.kind);
    const price = isSale ? (p.sale_price||p.wholesale_price||0) : (p.purchase_price||0);
    row.querySelector('.iprice').value = price;
    row.querySelector('.iwar').value = p.warranty_months||0;
    if(!row.querySelector('.idesc').value) row.querySelector('.idesc').value = p.name;
    if(!row.querySelector('.iprod').dataset.cost) row.querySelector('.iprod').dataset.cost = p.purchase_price||0;
    this.invRecalc();
  },

  invRecalc(){
    const isSale = ['sale','proforma','sale_return'].includes(this._inv.kind);
    const disc = Number(document.getElementById('iv_disc').value)||0;
    const rows = [...document.querySelectorAll('#iv_items tr')];
    let grossNet=0, sub=0;
    const data = rows.map(tr=>{
      const q=Number(tr.querySelector('.iqty').value)||0;
      const pr=Number(tr.querySelector('.iprice').value)||0;
      const d=Number(tr.querySelector('.idisc').value)||0;
      const g=q*pr; const n=Math.max(g-d,0); sub+=g; grossNet+=n;
      return {tr,q,pr,d,g,n};
    });
    let taxTotal=0, allocated=0, net=0;
    data.forEach((x,idx)=>{
      const share = grossNet>0 ? x.n/grossNet : 1/(data.length||1);
      let invPart = disc*share; if(idx===data.length-1) invPart = disc-allocated; allocated+=invPart;
      const taxable = Math.max(x.n-invPart,0);
      const rate = Number(x.tr.querySelector('.itax').value)||0;
      const t = taxable*rate/100; taxTotal+=t; net+=taxable;
      x.tr.querySelector('.iline').textContent = money(taxable+t);
    });
    const total = net+taxTotal;
    const cash=Number(document.getElementById('iv_cash').value)||0;
    const card=Number(document.getElementById('iv_card').value)||0;
    const chq=Number(document.getElementById('iv_cheque').value)||0;
    const paid=cash+card+chq; const remain=total-paid;
    document.getElementById('iv_totals').innerHTML = `
      <div class="row"><span>جمع اقلام</span><span class="num">${money(sub)}</span></div>
      <div class="row"><span>تخفیف</span><span class="num">${money(sub-net)}</span></div>
      <div class="row"><span>مالیات</span><span class="num">${money(taxTotal)}</span></div>
      <div class="row total"><span>مبلغ قابل پرداخت</span><span class="num">${money(total)}</span></div>
      <div class="row"><span>پرداختی</span><span class="num">${money(paid)}</span></div>
      <div class="row"><span>مانده (نسیه)</span><span class="num ${remain>0?'neg':'pos'}">${money(remain)}</span></div>`;
    this._inv._remaining = remain; this._inv._total = total;
    const btn = document.querySelector('.modal-foot .btn.primary');
    return {total, remain};
  },

  async invSave(){
    const items = [...document.querySelectorAll('#iv_items tr')].map(tr=>{
      const pid = tr.querySelector('.iprod').value;
      const prod = (this.cache.products||[]).find(x=>String(x.id)===String(pid));
      return { product_id: pid||null,
        description: tr.querySelector('.idesc').value,
        qty: Number(tr.querySelector('.iqty').value)||0,
        unit_price: Number(tr.querySelector('.iprice').value)||0,
        discount: Number(tr.querySelector('.idisc').value)||0,
        tax_rate: Number(tr.querySelector('.itax').value)||0,
        serial: tr.querySelector('.iserial').value,
        warranty_months: Number(tr.querySelector('.iwar').value)||0,
        cost_price: prod ? Number(prod.purchase_price)||0 : 0 };
    });
    const d = { kind:this._inv.kind, number:document.getElementById('iv_number').value,
      date:fieldVal('iv_date'), party_id:fieldVal('iv_party')||null,
      warehouse_id:fieldVal('iv_wh')||null, discount:Number(document.getElementById('iv_disc').value)||0,
      tax_rate:Number(document.getElementById('iv_taxrate').value)||0,
      paid_cash:Number(document.getElementById('iv_cash').value)||0,
      paid_card:Number(document.getElementById('iv_card').value)||0,
      paid_cheque:Number(document.getElementById('iv_cheque').value)||0,
      status:document.getElementById('iv_status').value,
      note:document.getElementById('iv_note').value, items };
    if(!d.party_id){ toast('طرف حساب را انتخاب کنید','error'); return; }
    if(!JDate.isValid(d.date)){ toast('تاریخ نامعتبر است','error'); return; }
    const res = await apiTry('invoices' + (this._inv.id?('/'+this._inv.id):''), {method: this._inv.id?'PUT':'POST', body:d});
    if(res !== null){ this.closeModal(); toast('فاکتور با موفقیت ذخیره شد','ok'); await this.refreshCache(); this.navigate('invoices-'+this._inv.kind); }
  },

  async delInvoice(id){
    if(!confirm('این فاکتور حذف شود؟ اثرات انبار و حساب‌ها نیز برگشت داده می‌شود.')) return;
    await apiTry('invoices/'+id, {method:'DELETE'});
    this.navigate(this.route);
  },

  quickInvoice(kind){ this.invoiceEditor(kind); },

  /* ------------------------------ انبارداری ----------------------------- */
  async v_inventory(){
    const rows = await api('reports/inventory');
    const totalVal = rows.reduce((s,r)=>s+(r.value||0),0);
    const cols = [
      {title:'کد', key:'code'},
      {title:'نام کالا', render:r=>`<b>${esc(r.name)}</b>`},
      {title:'گروه', render:r=>esc(r.group_name||'—')},
      {title:'واحد', render:r=>esc(r.unit_name||'—')},
      {title:'موجودی', render:r=>`<span class="badge ${r.low?'red':'blue'}">${qtyf(r.stock)}</span>`},
      {title:'حد سفارش', render:r=>qtyf(r.reorder_level)},
      {title:'قیمت خرید', render:r=>`<span class="num">${money(r.purchase_price)}</span>`},
      {title:'ارزش موجودی', render:r=>`<span class="num">${money(r.value)}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('موجودی کالا',
      `<button class="btn" onclick="App.navigate('inventory-transfer')">انتقال بین انبار</button>
       <button class="btn" onclick="App.navigate('inventory-adjust')">اصلاح موجودی</button>
       <a class="btn" href="/api/export/inventory">خروجی اکسل</a>`,
      `<div class="card"><div class="hint" style="margin-bottom:10px">ارزش کل موجودی انبار: <b>${money(totalVal)} ${this.cur()}</b></div>${table(cols, rows)}</div>`);
  },

  async v_inventorycardex(){
    const cards = this.cache.products||[];
    const cur = this._cardexProduct || (cards[0]&&cards[0].id) || '';
    const wh = this._cardexWh || '';
    let rows = [];
    if(cur) rows = await api(`stock/moves?product_id=${cur}${wh?('&warehouse_id='+wh):''}`);
    const cols = [
      {title:'تاریخ', key:'date'},
      {title:'شرح', render:r=>esc(r.description||'')},
      {title:'انبار', render:r=>esc(r.warehouse_name||'—')},
      {title:'ورود', render:r=>r.qty_in?`<span class="num pos">${qtyf(r.qty_in)}</span>`:''},
      {title:'خروج', render:r=>r.qty_out?`<span class="num neg">${qtyf(r.qty_out)}</span>`:''},
      {title:'مانده', render:r=>`<span class="num">${qtyf(r.balance)}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('گردش کالا (کاردکس)', '',
      `<div class="card"><div class="inline" style="margin-bottom:12px">
        <div class="field"><label>کالا</label><select id="cd_prod">${cards.map(c=>`<option value="${c.id}" ${String(c.id)===String(cur)?'selected':''}>${esc(c.name)}</option>`).join('')}</select></div>
        <div class="field"><label>انبار</label><select id="cd_wh"><option value="">همه انبارها</option>${this.optWarehouses(wh)}</select></div>
        <button class="btn primary" onclick="App._cardexProduct=document.getElementById('cd_prod').value;App._cardexWh=document.getElementById('cd_wh').value;App.navigate('inventory-cardex')">نمایش</button>
      </div>${table(cols, rows)}</div>`);
  },

  async v_inventorytransfer(){
    const body = `<div class="form-grid c2">
      ${field({name:'t_date',label:'تاریخ',type:'date',value:this.meta.today})}
      <div class="field"><label>کالا</label><select id="t_prod">${this.optProducts()}</select></div>
      <div class="field"><label>از انبار</label><select id="t_src">${this.optWarehouses()}</select></div>
      <div class="field"><label>به انبار</label><select id="t_dst">${this.optWarehouses()}</select></div>
      <div class="field"><label>مقدار</label><input id="t_qty" type="number" value="1"></div>
      <div class="field"><label>توضیح</label><input id="t_desc" value=""></div></div>`;
    $('#content').innerHTML = this.dwrap('انتقال بین انبار', '', `<div class="card">${body}
      <button class="btn primary" onclick="App.doTransfer()">ثبت انتقال</button></div>`);
  },
  async doTransfer(){
    const d = {date:fieldVal('t_date'), product_id:fieldVal('t_prod'), src:fieldVal('t_src'),
      dst:fieldVal('t_dst'), qty:Number(fieldVal('t_qty'))||0, description:fieldVal('t_desc')};
    if(d.src===d.dst){ toast('انبار مبدأ و مقصد یکسان است','error'); return; }
    const r = await apiTry('stock/transfer', {method:'POST', body:d});
    if(r!==null){ toast('انتقال انجام شد','ok'); this.navigate('inventory-transfer'); }
  },

  async v_inventoryadjust(){
    const body = `<div class="form-grid c2">
      ${field({name:'a_date',label:'تاریخ',type:'date',value:this.meta.today})}
      <div class="field"><label>کالا</label><select id="a_prod">${this.optProducts()}</select></div>
      <div class="field"><label>انبار</label><select id="a_wh">${this.optWarehouses()}</select></div>
      <div class="field"><label>نوع عملیات</label><select id="a_dir"><option value="in">افزایش موجودی</option><option value="out">کاهش موجودی</option></select></div>
      <div class="field"><label>مقدار</label><input id="a_qty" type="number" value="1"></div>
      <div class="field"><label>بهای واحد (اختیاری)</label><input id="a_cost" type="number" value="0"></div>
      <div class="field"><label>توضیح</label><input id="a_desc" value=""></div></div>`;
    $('#content').innerHTML = this.dwrap('اصلاح موجودی انبار', '', `<div class="card">${body}
      <button class="btn primary" onclick="App.doAdjust()">ثبت اصلاح موجودی</button></div>`);
  },
  async doAdjust(){
    const d = {date:fieldVal('a_date'), product_id:fieldVal('a_prod'), warehouse_id:fieldVal('a_wh'),
      direction:fieldVal('a_dir'), qty:Number(fieldVal('a_qty'))||0,
      unit_cost:Number(fieldVal('a_cost'))||0, description:fieldVal('a_desc')};
    const r = await apiTry('stock/adjust', {method:'POST', body:d});
    if(r!==null){ toast('موجودی اصلاح شد','ok'); this.navigate('inventory'); }
  },

  /* ------------------------------ حسابداری ------------------------------ */
  async v_accountingreceipts(){
    const rows = await api('receipts');
    const cols = [
      {title:'شماره', key:'number'},
      {title:'تاریخ', key:'date'},
      {title:'نوع', render:r=>`<span class="badge ${r.kind==='receive'?'green':'amber'}">${r.kind==='receive'?'دریافت':'پرداخت'}</span>`},
      {title:'طرف حساب', render:r=>esc(r.party_name||'—')},
      {title:'روش', render:r=>r.method==='cash'?'نقد':r.method==='card'?'کارت/بانک':'سایر'},
      {title:'مبلغ', render:r=>`<span class="num">${money(r.amount)}</span>`},
      {title:'شرح', render:r=>esc(r.description||'')},
      {title:'عملیات', render:r=>`<button class="btn small danger" onclick="App.delReceipt(${r.id})">حذف</button>`},
    ];
    $('#content').innerHTML = this.dwrap('دریافت و پرداخت وجه',
      `<button class="btn green" onclick="App.receiptForm('receive')">+ دریافت وجه</button>
       <button class="btn" onclick="App.receiptForm('pay')">+ پرداخت وجه</button>`,
      `<div class="card">${table(cols, rows)}</div>`);
  },
  receiptForm(kind){
    const fields = [
      {name:'r_date', label:'تاریخ', type:'date', value:this.meta.today},
      {name:'r_party', label:'طرف حساب', type:'select', options:[]},
      {name:'r_amount', label:'مبلغ', type:'number', value:0},
      {name:'r_method', label:'روش', type:'select', value:'cash', options:[{value:'cash',label:'نقد (صندوق)'},{value:'card',label:'کارت / بانک'}]},
      {name:'r_ref', label:'شماره فاکتور مرتبط', value:''},
      {name:'r_desc', label:'شرح', value:''},
    ];
    modalForm(kind==='receive'?'ثبت دریافت وجه':'ثبت پرداخت وجه', fields, null,
      `<button class="btn primary" onclick="App.saveReceipt('${kind}')">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
    document.getElementById('f_r_party').innerHTML = this.optEmpty() + this.optParties();
  },
  async saveReceipt(kind){
    const d = {kind, date:fieldVal('r_date'), party_id:fieldVal('r_party')||null,
      amount:fieldNum('r_amount'), method:fieldVal('r_method'),
      ref_invoice:fieldVal('r_ref'), description:fieldVal('r_desc')};
    if(d.amount<=0){ toast('مبلغ را وارد کنید','error'); return; }
    const r = await apiTry('receipts', {method:'POST', body:d});
    if(r!==null){ this.closeModal(); toast('سند ثبت شد','ok'); this.navigate('accounting-receipts'); }
  },
  async delReceipt(id){ if(!confirm('حذف شود؟')) return; await apiTry('receipts/'+id,{method:'DELETE'}); this.navigate('accounting-receipts'); },

  async v_accountingjournal(){
    const q=this._jq||'', df=this._jf||'', dt=this._jt||'';
    const rows = await api(`reports/journal?q=${encodeURIComponent(q)}&from=${df}&to=${dt}`);
    const cols = [
      {title:'شماره سند', key:'number'},
      {title:'تاریخ', key:'date'},
      {title:'شرح', render:r=>esc(r.description||'')},
      {title:'مبلغ', render:r=>`<span class="num">${money(r.sum_debit)}</span>`},
      {title:'ثبت‌کننده', render:r=>esc(r.username||'')},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.journalView(${r.id})">مشاهده</button>
        <button class="btn small danger" onclick="App.delJournal(${r.id})">حذف</button>`},
    ];
    $('#content').innerHTML = this.dwrap('اسناد حسابداری',
      `<button class="btn primary" onclick="App.manualVoucher()">+ سند دستی</button>`,
      `<div class="card"><div class="inline" style="margin-bottom:12px">
        <div class="field"><input id="jq" value="${esc(q)}" placeholder="شرح یا شماره سند..."></div>
        <div class="field"><input id="jf" value="${esc(df)}" placeholder="از تاریخ"></div>
        <div class="field"><input id="jt" value="${esc(dt)}" placeholder="تا تاریخ"></div>
        <button class="btn" onclick="App._jq=document.getElementById('jq').value;App._jf=document.getElementById('jf').value;App._jt=document.getElementById('jt').value;App.navigate('accounting-journal')">فیلتر</button></div>
        ${table(cols, rows)}</div>`);
  },
  async journalView(id){
    const d = await api('journal/'+id);
    const cols = [
      {title:'حساب', key:'account'},
      {title:'شرح', render:r=>esc(r.description||'')},
      {title:'بدهکار', render:r=>r.debit?`<span class="num">${money(r.debit)}</span>`:''},
      {title:'بستانکار', render:r=>r.credit?`<span class="num">${money(r.credit)}</span>`:''},
    ];
    modal('سند ' + esc(d.journal.number) + ' — ' + esc(d.journal.date),
      `<div class="hint" style="margin-bottom:10px">${esc(d.journal.description||'')}</div>` + table(cols, d.lines),
      `<button class="btn" onclick="App.closeModal()">بستن</button>`, true);
  },
  async delJournal(id){ if(!confirm('سند حذف شود؟')) return; await apiTry('journal/'+id,{method:'DELETE'}); this.navigate('accounting-journal'); },
  manualVoucher(){
    this._vlines = [{account:'',description:'',debit:0,credit:0},{account:'',description:'',debit:0,credit:0}];
    modal('ثبت سند حسابداری دستی',
      `<div class="form-grid c3">${field({name:'v_date',label:'تاریخ',type:'date',value:this.meta.today})}
        ${field({name:'v_desc',label:'شرح سند'})}<div></div></div>
       <div class="scroll-x"><table><thead><tr><th>حساب</th><th>شرح</th><th>بدهکار</th><th>بستانکار</th><th></th></tr></thead>
       <tbody id="v_lines"></tbody></table></div>
       <button class="btn small" style="margin-top:8px" onclick="App.vAddLine()">+ ردیف</button>
       <div id="v_balance" class="hint" style="margin-top:10px"></div>`,
      `<button class="btn primary" onclick="App.saveVoucher()">ذخیره سند</button><button class="btn" onclick="App.closeModal()">انصراف</button>`, true);
    this.vRenderLines();
  },
  vRenderLines(){
    document.getElementById('v_lines').innerHTML = this._vlines.map((l,i)=>`<tr>
      <td><select data-i="${i}" onchange="App._vlines[${i}].account=this.value;App.vBalance()">${this.optEmpty()}${this.optAccounts(l.account)}</select></td>
      <td><input value="${esc(l.description||'')}" oninput="App._vlines[${i}].description=this.value"></td>
      <td><input type="number" value="${l.debit||0}" oninput="App._vlines[${i}].debit=Number(this.value)||0;App.vBalance()"></td>
      <td><input type="number" value="${l.credit||0}" oninput="App._vlines[${i}].credit=Number(this.value)||0;App.vBalance()"></td>
      <td><button class="btn small danger" onclick="App.vRemoveLine(${i})">✕</button></td></tr>`).join('');
    this.vBalance();
  },
  vAddLine(){ this._vlines.push({account:'',description:'',debit:0,credit:0}); this.vRenderLines(); },
  vRemoveLine(i){ this._vlines.splice(i,1); this.vRenderLines(); },
  vBalance(){
    const deb=this._vlines.reduce((s,l)=>s+(Number(l.debit)||0),0);
    const cred=this._vlines.reduce((s,l)=>s+(Number(l.credit)||0),0);
    const ok = Math.abs(deb - cred) < 1;
    document.getElementById('v_balance').innerHTML =
      `جمع بدهکار: <b>${money(deb)}</b> — جمع بستانکار: <b>${money(cred)}</b> — ` +
      (ok ? `<span class="pos">${ic('check')} سند تراز است</span>`
          : `<span class="neg">${ic('warning')} سند تراز نیست</span>`);
  },
  async saveVoucher(){
    const lines = this._vlines.filter(l=>l.account);
    const d = {date:fieldVal('v_date'), description:fieldVal('v_desc'), lines};
    const r = await apiTry('journal', {method:'POST', body:d});
    if(r!==null){ this.closeModal(); toast('سند ثبت شد','ok'); this.navigate('accounting-journal'); }
  },

  async v_accountingtrial(){
    const rows = await api('reports/trial-balance');
    const td = rows.reduce((s,r)=>s+r.debit,0), tc = rows.reduce((s,r)=>s+r.credit,0);
    const cols = [
      {title:'حساب', render:r=>`<b>${esc(r.account)}</b>`},
      {title:'نوع', render:r=>`<span class="badge neutral">${this.accType(r.type)}</span>`},
      {title:'بدهکار', render:r=>`<span class="num">${money(r.debit)}</span>`},
      {title:'بستانکار', render:r=>`<span class="num">${money(r.credit)}</span>`},
      {title:'مانده', render:r=>`<span class="num ${r.balance>=0?'pos':'neg'}">${money(Math.abs(r.balance))} ${r.balance>=0?'بد':'بس'}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('تراز آزمایشی', '', `<div class="card">
      <div class="hint" style="margin-bottom:10px">جمع بدهکار: <b>${money(td)}</b> — جمع بستانکار: <b>${money(tc)}</b> ${Math.abs(td-tc)<1?`<span class="pos">${ic('check')} تراز است</span>`:`<span class="neg">${ic('warning')} عدم تراز</span>`}</div>
      ${table(cols, rows)}</div>`);
  },
  accType(t){ return {asset:'دارایی',liability:'بدهی',equity:'سرمایه',revenue:'درآمد',expense:'هزینه'}[t]||'—'; },

  async v_accountingpl(){
    const df=this._plf||this.meta.settings.fiscal_year_start||'', dt=this._plt||'';
    const d = await api(`reports/profit-loss?from=${df}&to=${dt}`);
    const row = (l,v,cls)=>`<div class="row" style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px dashed var(--line)"><span>${l}</span><span class="num ${cls||''}">${money(v)}</span></div>`;
    $('#content').innerHTML = this.dwrap('صورت سود و زیان', '', `<div class="card">
      <div class="inline" style="margin-bottom:14px">
        <div class="field"><label>از تاریخ</label><input id="plf" value="${esc(df)}"></div>
        <div class="field"><label>تا تاریخ</label><input id="plt" value="${esc(dt)}"></div>
        <button class="btn" onclick="App._plf=document.getElementById('plf').value;App._plt=document.getElementById('plt').value;App.navigate('accounting-pl')">محاسبه</button></div>
      <div class="grid cols-2"><div><div class="card-title">درآمدها</div>${d.revenue.map(r=>row(r.account,r.amount,'pos')).join('')||'<div class="muted">—</div>'}
        ${row('جمع درآمد', d.total_revenue,'pos')}</div>
      <div><div class="card-title">هزینه‌ها</div>${d.expense.map(r=>row(r.account,r.amount,'neg')).join('')||'<div class="muted">—</div>'}
        ${row('جمع هزینه', d.total_expense,'neg')}</div></div>
      <div class="totals" style="margin-top:16px"><div class="row total"><span>سود / زیان دوره</span><span class="num ${d.profit>=0?'pos':'neg'}">${money(d.profit)}</span></div></div></div>`);
  },

  async v_accountingbs(){
    const d = await api('reports/balance-sheet');
    const row = (l,v)=>`<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px dashed var(--line)"><span>${esc(l)}</span><span class="num">${money(v)}</span></div>`;
    $('#content').innerHTML = this.dwrap('ترازنامه', '', `<div class="card">
      <div class="grid cols-2"><div><div class="card-title">دارایی‌ها</div>${d.assets.map(a=>row(a.account,a.amount)).join('')}
        ${row('جمع دارایی‌ها', d.total_assets)}</div>
      <div><div class="card-title">بدهی‌ها</div>${d.liabilities.map(a=>row(a.account,a.amount)).join('')}
        ${row('جمع بدهی‌ها', d.total_liabilities)}
        <div class="card-title" style="margin-top:12px">حقوق صاحبان سهام</div>
        ${row('سرمایه و سود انباشته', d.equity)}</div></div>
      <div class="totals" style="margin-top:16px"><div class="row total"><span>جمع دارایی‌ها</span><span class="num">${money(d.total_assets)}</span></div></div></div>`);
  },

  /* -------------------------------- چک‌ها -------------------------------- */
  async v_chequesreceivable(){ await this.chequeList('receivable'); },
  async v_chequespayable(){ await this.chequeList('payable'); },
  async chequeList(ctype){
    const rows = await api('cheques?ctype='+ctype);
    const statusName = {in_hand:'نزد ما', spent:'خرج‌شده', cleared:'پاس‌شده', deposited:'به حساب گذاشته', returned:'برگشتی'};
    const cols = [
      {title:'شماره چک', key:'number'},
      {title:'طرف حساب', render:r=>esc(r.party_name||'—')},
      {title:'بانک', render:r=>esc(r.bank||'—')},
      {title:'مبلغ', render:r=>`<span class="num">${money(r.amount)}</span>`},
      {title:'تاریخ صدور', key:'issue_date'},
      {title:'سررسید', key:'due_date'},
      {title:'وضعیت', render:r=>`<span class="badge ${r.status==='cleared'?'green':r.status==='returned'?'red':'amber'}">${statusName[r.status]||r.status}</span>`},
      {title:'ضمانتی', render:r=>r.is_guarantee?'<span class="badge info">بله</span>':'—'},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.chequeStatus(${r.id},'${r.status}')">تغییر وضعیت</button>
        <button class="btn small" onclick="App.editCheque(${r.id},'${ctype}')">ویرایش</button>
        <button class="btn small danger" onclick="App.delCheque(${r.id})">حذف</button>`},
    ];
    const title = ctype==='receivable'?'چک‌های دریافتنی (اسناد دریافتنی)':'چک‌های پرداختنی (اسناد پرداختنی)';
    $('#content').innerHTML = this.dwrap(title,
      `<button class="btn primary" onclick="App.editCheque(0,'${ctype}')">+ چک جدید</button>
       <button class="btn" onclick="App.navigate('cheques-due')">سررسید چک‌ها</button>`,
      `<div class="card">${table(cols, rows)}</div>`);
  },
  editCheque(id, ctype){
    const c = id ? this._chequesCache?.find(x=>x.id===id) : null;
    const fields = [
      {name:'c_number', label:'شماره چک', value:c?c.number:''},
      {name:'c_party', label:'طرف حساب', type:'select', options:[]},
      {name:'c_bank', label:'نام بانک', value:c?c.bank:''},
      {name:'c_branch', label:'شعبه', value:c?c.branch:''},
      {name:'c_account', label:'شماره حساب', value:c?c.account:''},
      {name:'c_amount', label:'مبلغ چک', type:'number', value:c?c.amount:0},
      {name:'c_issue', label:'تاریخ صدور', type:'date', value:c?c.issue_date:this.meta.today},
      {name:'c_due', label:'تاریخ سررسید', type:'date', value:c?c.due_date:this.meta.today},
      {name:'c_status', label:'وضعیت', type:'select', value:c?c.status:'in_hand', options:[{value:'in_hand',label:'نزد ما'},{value:'spent',label:'خرج‌شده'},{value:'deposited',label:'به حساب گذاشته'},{value:'cleared',label:'پاس‌شده'},{value:'returned',label:'برگشتی'}]},
      {name:'c_guarantee', label:'چک ضمانتی است؟', type:'select', value:c&&c.is_guarantee?'1':'0', options:[{value:'0',label:'خیر'},{value:'1',label:'بله'}]},
      {name:'c_note', label:'توضیحات', type:'textarea', value:c?c.note:''},
    ];
    modalForm((id?'ویرایش':'ثبت') + (ctype==='receivable'?' چک دریافتنی':' چک پرداختنی'), fields, null,
      `<button class="btn primary" onclick="App.saveCheque(${id||0},'${ctype}')">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
    document.getElementById('f_c_party').innerHTML = this.optEmpty() + this.optParties(c?c.party_id:'');
  },
  async saveCheque(id, ctype){
    const d = {number:fieldVal('c_number'), ctype, party_id:fieldVal('c_party')||null,
      bank:fieldVal('c_bank'), branch:fieldVal('c_branch'), account:fieldVal('c_account'),
      amount:fieldNum('c_amount'), issue_date:fieldVal('c_issue'), due_date:fieldVal('c_due'),
      status:fieldVal('c_status'), is_guarantee:Number(fieldVal('c_guarantee'))||0,
      note:fieldVal('c_note')};
    if(d.amount<=0){ toast('مبلغ چک را وارد کنید','error'); return; }
    const r = await apiTry('cheques' + (id?('/'+id):''), {method:id?'PUT':'POST', body:d});
    if(r!==null){ this.closeModal(); toast('چک ذخیره شد','ok'); this.navigate('cheques-'+(ctype==='receivable'?'receivable':'payable')); }
  },
  async chequeStatus(id, current){
    const opts = ['in_hand','spent','deposited','cleared','returned'];
    const names = {in_hand:'نزد ما', spent:'خرج‌شده', deposited:'به حساب گذاشته', cleared:'پاس‌شده', returned:'برگشتی'};
    const f = [{name:'cs', label:'وضعیت جدید', type:'select', value:current, options:opts.map(o=>({value:o,label:names[o]}))}];
    modalForm('تغییر وضعیت چک', f, null, `<button class="btn primary" onclick="App.doChequeStatus(${id})">ثبت</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },
  async doChequeStatus(id){
    const all = await api('cheques'); const c = all.find(x=>x.id===id);
    const body = {...c, status:fieldVal('cs'), is_guarantee:c.is_guarantee};
    const r = await apiTry('cheques/'+id, {method:'PUT', body});
    if(r!==null){ this.closeModal(); toast('وضعیت چک تغییر کرد','ok'); this.navigate(this.route); }
  },
  async delCheque(id){ if(!confirm('چک حذف شود؟')) return; await apiTry('cheques/'+id,{method:'DELETE'}); this.navigate(this.route); },

  async v_chequesdue(){
    const rows = await api('reports/cheque-due?days=3650');
    const cols = [
      {title:'شماره چک', key:'number'},
      {title:'نوع', render:r=>`<span class="badge ${r.ctype==='receivable'?'green':'amber'}">${r.ctype==='receivable'?'دریافتنی':'پرداختنی'}</span>`},
      {title:'طرف حساب', render:r=>esc(r.party_name||'—')},
      {title:'سررسید', key:'due_date'},
      {title:'روز مانده', render:r=>r.days_left<0?'<span class="badge bad">سررسید گذشته</span>':`<span class="badge ${r.days_left<=7?'amber':'gray'}">${nf.format(r.days_left)} روز</span>`},
      {title:'مبلغ', render:r=>`<span class="num">${money(r.amount)}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('سررسید چک‌ها', `<button class="btn" onclick="App.navigate('cheques-receivable')">چک‌های دریافتنی</button>
      <button class="btn" onclick="App.navigate('cheques-payable')">چک‌های پرداختنی</button>`,
      `<div class="card">${table(cols, rows)}</div>`);
  },

  /* ------------------------- صنف باتری: سریال و گارانتی ------------------ */
  async v_batteryserials(){
    const q = this._serq||''; const st = this._serst||'';
    const rows = await api(`serials?q=${encodeURIComponent(q)}&status=${st}`);
    const cols = [
      {title:'سریال', render:r=>`<b>${esc(r.serial)}</b>`},
      {title:'کالا', render:r=>esc(r.product_name||'—')},
      {title:'مشتری', render:r=>esc(r.party_name||'—')},
      {title:'تاریخ فروش', render:r=>esc(r.sold_at||'—')},
      {title:'گارانتی تا', render:r=>esc(r.warranty_end||'—')},
      {title:'اعتبار گارانتی', render:r=>r.warranty_end?(r.warranty_active?'<span class="badge ok">دارای گارانتی</span>':'<span class="badge neutral">منقضی</span>'):'—'},
      {title:'وضعیت', render:r=>`<span class="badge ${r.status==='sold'?'blue':r.status==='returned'?'amber':r.status==='scrap'?'red':'gray'}">${this.serialStatus(r.status)}</span>`},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.serialClaim(${r.id})">مرجوعی گارانتی</button>
        <button class="btn small danger" onclick="App.serialToScrap(${r.id})">تبدیل به فرسوده</button>`},
    ];
    $('#content').innerHTML = this.dwrap('سریال و گارانتی باتری',
      `<button class="btn" onclick="App.navigate('battery-scrap')">خرید باتری فرسوده</button>`,
      `<div class="card"><div class="inline" style="margin-bottom:12px">
        <div class="field"><input id="serq" value="${esc(q)}" placeholder="جستجوی سریال یا کالا..."></div>
        <div class="field"><select id="serst"><option value="">همه وضعیت‌ها</option>
          ${['sold','returned','scrap','in_stock'].map(s=>`<option value="${s}" ${st===s?'selected':''}>${this.serialStatus(s)}</option>`).join('')}</select></div>
        <button class="btn" onclick="App._serq=document.getElementById('serq').value;App._serst=document.getElementById('serst').value;App.navigate('battery-serials')">فیلتر</button></div>
        ${table(cols, rows, {empty:'سریالی ثبت نشده است. سریال هنگام فروش باتری از فاکتور ثبت می‌شود.'})}</div>`);
  },
  serialStatus(s){ return {in_stock:'در انبار', sold:'فروش‌رفته', returned:'مرجوعی گارانتی', scrap:'تبدیل به ضایعات'}[s]||s; },
  async serialClaim(id){
    const f = [{name:'cl_note', label:'توضیح مرجوعی', type:'textarea', value:''}];
    modalForm('ثبت مرجوعی گارانتی', f, null, `<button class="btn primary" onclick="App.doSerialClaim(${id})">ثبت مرجوعی</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },
  async doSerialClaim(id){ const r = await apiTry('serials/claim', {method:'POST', body:{serial_id:id, note:fieldVal('cl_note')}});
    if(r!==null){ this.closeModal(); toast('مرجوعی گارانتی ثبت شد','ok'); this.navigate('battery-serials'); } },
  async serialToScrap(id){
    const f = [{name:'sc_weight', label:'وزن باتری فرسوده (کیلوگرم)', type:'number', value:0},
      {name:'sc_price', label:'قیمت هر کیلوگرم', type:'number', value:0},
      {name:'sc_date', label:'تاریخ', type:'date', value:this.meta.today},
      {name:'sc_method', label:'نحوه خرید', type:'select', value:'cash', options:[{value:'cash',label:'نقدی'},{value:'credit',label:'نسیه'}]},
      {name:'sc_desc', label:'توضیح', value:'تبدیل باتری مرجوعی به ضایعات'}];
    modalForm('تبدیل به باتری فرسوده (ضایعات)', f, null, `<button class="btn primary" onclick="App.doSerialToScrap(${id})">ثبت</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },
  async doSerialToScrap(id){
    const d = {serial_id:id, weight_kg:fieldNum('sc_weight'), price_per_kg:fieldNum('sc_price'),
      qty:1, date:fieldVal('sc_date'), method:fieldVal('sc_method'), description:fieldVal('sc_desc')};
    const r = await apiTry('serials/scrap', {method:'POST', body:d});
    if(r!==null){ this.closeModal(); toast('باتری به ضایعات منتقل شد','ok'); this.navigate('battery-serials'); }
  },

  /* --------------------------- باتری فرسوده / ضایعات ---------------------- */
  async v_batteryscrap(){
    const rows = await api('scrap');
    const st = await api('scrap/stock');
    const cols = [
      {title:'تاریخ', key:'date'},
      {title:'مشتری', render:r=>esc(r.party_name||'——')},
      {title:'برند', render:r=>esc(r.brand||'—')},
      {title:'آمپر', render:r=>esc(r.amperage||'—')},
      {title:'نوع', render:r=>esc(r.battery_type||'—')},
      {title:'تعداد', render:r=>qtyf(r.qty)},
      {title:'وزن (kg)', render:r=>qtyf(r.weight_kg)},
      {title:'قیمت/kg', render:r=>`<span class="num">${money(r.price_per_kg)}</span>`},
      {title:'مبلغ', render:r=>`<span class="num">${money(r.amount)}</span>`},
      {title:'نحوه', render:r=>r.method==='cash'?'نقدی':'نسیه'},
      {title:'شرح', render:r=>esc(r.description||'')},
      {title:'عملیات', render:r=>`<button class="btn small danger" onclick="App.delScrap(${r.id})">حذف</button>`},
    ];
    $('#content').innerHTML = this.dwrap('خرید باتری فرسوده (ضایعات)',
      `<button class="btn primary" onclick="App.scrapForm()">+ ثبت باتری فرسوده</button>
       <button class="btn" onclick="App.navigate('battery-scrap-sales')">فروش ضایعات</button>`,
      `<div class="grid cols-3" style="margin-bottom:14px">
        <div class="stat"><div class="lbl">موجودی ضایعات (تعداد)</div><div class="val">${qtyf(st.qty)}</div></div>
        <div class="stat"><div class="lbl">وزن موجود ضایعات</div><div class="val">${qtyf(Math.round(st.weight))} کیلوگرم</div></div>
        <div class="stat"><div class="lbl">ارزش موجودی ضایعات</div><div class="val blue">${money(st.value)} ${this.cur()}</div></div></div>
       <div class="card">${table(cols, rows, {empty:'تاکنون باتری فرسوده‌ای ثبت نشده است'})}</div>`);
  },
  scrapForm(){
    const f = [
      {name:'s_date', label:'تاریخ', type:'date', value:this.meta.today},
      {name:'s_party', label:'مشتری (فروشنده باتری فرسوده)', type:'select', options:[]},
      {name:'s_brand', label:'برند', value:''},
      {name:'s_amp', label:'آمپر', value:''},
      {name:'s_type', label:'نوع باتری', value:''},
      {name:'s_qty', label:'تعداد', type:'number', value:1},
      {name:'s_weight', label:'وزن کل (کیلوگرم)', type:'number', value:0, step:'any'},
      {name:'s_pricekg', label:'قیمت هر کیلوگرم', type:'number', value:0},
      {name:'s_unitprice', label:'یا قیمت هر عدد', type:'number', value:0},
      {name:'s_amount', label:'مبلغ کل (خالی = محاسبه خودکار)', type:'number', value:0},
      {name:'s_method', label:'نحوه پرداخت', type:'select', value:'cash', options:[{value:'cash',label:'نقدی (صندوق)'},{value:'credit',label:'نسیه (به حساب مشتری)'}]},
      {name:'s_desc', label:'توضیحات', type:'textarea', value:''},
    ];
    modalForm('ثبت خرید باتری فرسوده', f, null,
      `<button class="btn primary" onclick="App.saveScrap()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
    document.getElementById('f_s_party').innerHTML = this.optEmpty() + this.optParties();
  },
  async saveScrap(){
    const d = {date:fieldVal('s_date'), party_id:fieldVal('s_party')||null,
      brand:fieldVal('s_brand'), amperage:fieldVal('s_amp'), battery_type:fieldVal('s_type'),
      qty:fieldNum('s_qty'), weight_kg:fieldNum('s_weight'), price_per_kg:fieldNum('s_pricekg'),
      unit_price:fieldNum('s_unitprice'), amount:fieldNum('s_amount'),
      method:fieldVal('s_method'), description:fieldVal('s_desc')};
    const r = await apiTry('scrap', {method:'POST', body:d});
    if(r!==null){ this.closeModal(); toast('باتری فرسوده ثبت شد','ok'); this.navigate('battery-scrap'); }
  },
  async delScrap(id){ if(!confirm('حذف شود؟')) return; await apiTry('scrap/'+id,{method:'DELETE'}); this.navigate('battery-scrap'); },
  quickScrap(){ this.scrapForm(); },

  async v_batteryscrapsales(){
    const rows = await api('scrap/sales');
    const st = await api('scrap/stock');
    const cols = [
      {title:'تاریخ', key:'date'},
      {title:'خریدار (بازیافت)', render:r=>esc(r.party_name||'—')},
      {title:'تعداد', render:r=>qtyf(r.qty)},
      {title:'وزن (kg)', render:r=>qtyf(r.weight_kg)},
      {title:'قیمت/kg', render:r=>`<span class="num">${money(r.price_per_kg)}</span>`},
      {title:'مبلغ', render:r=>`<span class="num">${money(r.amount)}</span>`},
      {title:'نحوه', render:r=>r.method==='cash'?'نقدی':'نسیه'},
    ];
    $('#content').innerHTML = this.dwrap('فروش ضایعات باتری',
      `<button class="btn primary" onclick="App.scrapSaleForm()">+ فروش ضایعات</button>
       <button class="btn" onclick="App.navigate('battery-scrap')">خرید باتری فرسوده</button>`,
      `<div class="hint" style="margin-bottom:12px">موجودی ضایعات: <b>${qtyf(Math.round(st.weight))} کیلوگرم</b> (تعداد ${qtyf(st.qty)})</div>
       <div class="card">${table(cols, rows, {empty:'فروش ضایعاتی ثبت نشده است'})}</div>`);
  },
  scrapSaleForm(){
    const f = [
      {name:'ss_date', label:'تاریخ', type:'date', value:this.meta.today},
      {name:'ss_party', label:'خریدار / بازیافت', type:'select', options:[]},
      {name:'ss_weight', label:'وزن (کیلوگرم)', type:'number', value:0, step:'any'},
      {name:'ss_qty', label:'تعداد', type:'number', value:0},
      {name:'ss_pricekg', label:'قیمت هر کیلوگرم', type:'number', value:0},
      {name:'ss_amount', label:'مبلغ کل (خالی = خودکار)', type:'number', value:0},
      {name:'ss_method', label:'نحوه دریافت', type:'select', value:'cash', options:[{value:'cash',label:'نقدی'},{value:'credit',label:'نسیه'}]},
      {name:'ss_desc', label:'توضیحات', type:'textarea', value:''},
    ];
    modalForm('ثبت فروش ضایعات', f, null,
      `<button class="btn primary" onclick="App.saveScrapSale()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`);
    document.getElementById('f_ss_party').innerHTML = this.optEmpty() + this.optParties();
  },
  async saveScrapSale(){
    const d = {date:fieldVal('ss_date'), party_id:fieldVal('ss_party')||null,
      weight_kg:fieldNum('ss_weight'), qty:fieldNum('ss_qty'),
      price_per_kg:fieldNum('ss_pricekg'), amount:fieldNum('ss_amount'),
      method:fieldVal('ss_method'), description:fieldVal('ss_desc')};
    const r = await apiTry('scrap/sales', {method:'POST', body:d});
    if(r!==null){ this.closeModal(); toast('فروش ضایعات ثبت شد','ok'); this.navigate('battery-scrap-sales'); }
  },

  /* ------------------------------- گزارشات ------------------------------ */
  async v_reportssales(){
    const df=this._rsf||this.meta.settings.fiscal_year_start||'', dt=this._rst||'';
    const rows = await api(`reports/sales-summary?from=${df}&to=${dt}`);
    const cols = [
      {title:'نوع فاکتور', render:r=>`<b>${this.kindName(r.kind)}</b>`},
      {title:'تعداد', render:r=>nf.format(r.c)},
      {title:'مبلغ کل', render:r=>`<span class="num">${money(r.t)}</span>`},
      {title:'بهای تمام‌شده', render:r=>`<span class="num">${money(r.cost)}</span>`},
      {title:'سود ناویژه', render:r=>`<span class="num ${r.kind==='sale'?'pos':''}">${money(r.t-r.cost)}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('گزارش جمع‌بندی فروش و خرید', '', `<div class="card">
      <div class="inline" style="margin-bottom:12px">
        <div class="field"><label>از تاریخ</label><input id="rsf" value="${esc(df)}"></div>
        <div class="field"><label>تا تاریخ</label><input id="rst" value="${esc(dt)}"></div>
        <button class="btn" onclick="App._rsf=document.getElementById('rsf').value;App._rst=document.getElementById('rst').value;App.navigate('reports-sales')">نمایش</button></div>
      ${table(cols, rows)}</div>`);
  },
  async v_reportsproducts(){
    const df=this._rpf||this.meta.settings.fiscal_year_start||'', dt=this._rpt||'';
    const rows = await api(`reports/product-sales?from=${df}&to=${dt}`);
    const cols = [
      {title:'نام کالا', render:r=>`<b>${esc(r.name||'—')}</b>`},
      {title:'تعداد فروش', render:r=>qtyf(r.qty)},
      {title:'مبلغ فروش', render:r=>`<span class="num">${money(r.total)}</span>`},
      {title:'بهای تمام‌شده', render:r=>`<span class="num">${money(r.cost)}</span>`},
      {title:'سود', render:r=>`<span class="num pos">${money(r.total-r.cost)}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('پرفروش‌ترین کالاها', '', `<div class="card">
      <div class="inline" style="margin-bottom:12px">
        <div class="field"><label>از تاریخ</label><input id="rpf" value="${esc(df)}"></div>
        <div class="field"><label>تا تاریخ</label><input id="rpt" value="${esc(dt)}"></div>
        <button class="btn" onclick="App._rpf=document.getElementById('rpf').value;App._rpt=document.getElementById('rpt').value;App.navigate('reports-products')">نمایش</button></div>
      ${table(cols, rows)}</div>`);
  },
  async v_reportsdebtors(){
    const rows = await api('reports/debtors');
    const cols = [
      {title:'نام شخص', render:r=>`<b>${esc(r.name)}</b>`},
      {title:'همراه', render:r=>esc(r.mobile||'—')},
      {title:'مانده', render:r=>r.balance>0?`<span class="badge bad">بدهکار ${money(r.balance)}</span>`:`<span class="badge ok">بستانکار ${money(-r.balance)}</span>`},
      {title:'عملیات', render:r=>`<button class="btn small" onclick="App.partyLedger(${r.id})">ریز حساب</button>`},
    ];
    const total = rows.reduce((s,r)=>s+(r.balance>0?r.balance:0),0);
    $('#content').innerHTML = this.dwrap('اشخاص بدهکار و بستانکار', '',
      `<div class="hint" style="margin-bottom:12px">جمع کل مطالبات (بدهکاران): <b>${money(total)} ${this.cur()}</b></div>
       <div class="card">${table(cols, rows, {empty:'همه حساب‌ها تسویه است'})}</div>`);
  },
  async v_reportsinventory(){
    const rows = await api('reports/inventory');
    const total = rows.reduce((s,r)=>s+(r.value||0),0);
    const cols = [
      {title:'کد', key:'code'},
      {title:'نام کالا', render:r=>esc(r.name)},
      {title:'برند', render:r=>esc(r.brand||'—')},
      {title:'آمپر', render:r=>esc(r.amperage||'—')},
      {title:'موجودی', render:r=>qtyf(r.stock)},
      {title:'قیمت خرید', render:r=>`<span class="num">${money(r.purchase_price)}</span>`},
      {title:'ارزش', render:r=>`<span class="num">${money(r.value)}</span>`},
    ];
    $('#content').innerHTML = this.dwrap('ارزش موجودی انبار', `<a class="btn" href="/api/export/inventory">خروجی اکسل</a>`,
      `<div class="hint" style="margin-bottom:12px">ارزش کل انبار: <b>${money(total)} ${this.cur()}</b></div>
       <div class="card">${table(cols, rows)}</div>`);
  },

  /* ------------------------------- لایسنس -------------------------------- */
  async v_license(){
    const info = await api('license');
    this.meta.license = info;
    this.renderNav();
    const feats = info.features || [];
    const featRows = Object.keys(FEATURE_LABELS).map(k => ({key:k, on:feats.indexOf(k)!==-1}));
    const state = info.valid
      ? '<span class="badge ok">فعال</span>'
      : '<span class="badge bad">غیرفعال</span>';
    const infoCard = `<div class="card">
        <div class="card-title">${ic('lock')}وضعیت لایسنس این نصب ${state}</div>
        <div class="grid cols-2" style="margin-top:12px">
          <div class="stack">
            ${rowsOf([
              ['وضعیت', esc(info.message || '—')],
              ['مشتری', esc(info.customer || '—')],
              ['نسخه', info.edition === 'premium' ? 'پرمیوم' : 'پایه'],
              ['سقف کاربران', esc(String(info.seats || 1)) + ' نفر'],
            ])}
          </div>
          <div class="stack">
            ${rowsOf([
              ['تاریخ صدور', esc(info.issued || '—')],
              ['تاریخ انقضا', esc(info.expires || 'بدون انقضا')],
              ['روزهای باقی‌مانده', info.days_left == null ? '—' : esc(String(info.days_left))],
              ['کد این رایانه', `<span class="mono">${esc(info.machine_code || '—')}</span>`],
            ])}
          </div>
        </div>
        ${info.clock_tampered ? `<div class="hint bad" style="margin-top:12px">
            <span class="ico">${ic('warning')}</span><span>ساعت سیستم از آخرین اجرای برنامه
            عقب‌تر است؛ لایسنس قفل شده. ساعت ویندوز را درست کنید.</span></div>` : ''}
      </div>`;

    const featureCard = `<div class="card">
        <div class="card-title">${ic('check')}قابلیت‌های در دسترس</div>
        <div class="table-wrap compact" style="margin-top:10px"><table><tbody>
        ${featRows.map(f => `<tr><td>${esc(FEATURE_LABELS[f.key])}</td>
          <td style="width:90px">${f.on
            ? '<span class="badge ok">باز</span>'
            : '<span class="badge neutral">بسته</span>'}</td></tr>`).join('')}
        </tbody></table></div>
        ${info.valid ? '' : `<div class="hint warn" style="margin-top:10px">
          <span class="ico">${ic('info')}</span><span>برای باز شدن این قابلیت‌ها،
          لایسنس پرمیوم این رایانه را فعال کنید.</span></div>`}
      </div>`;

    const activateCard = `<div class="card">
        <div class="card-title">${ic('keyboard')}فعال‌سازی / تعویض لایسنس</div>
        <p class="muted small">کد این رایانه: <b class="mono">${esc(info.machine_code||'—')}</b>
           — آن را برای صدور لایسنس به فروشنده بدهید.</p>
        <div class="field"><label for="licKeyNew">متن لایسنس یا محتوای فایل .key</label>
          <textarea id="licKeyNew" rows="4" spellcheck="false" placeholder="SABA1.…"></textarea></div>
        <button class="btn primary" onclick="App.activateHere()">
          ${ic('check')}فعال‌سازی روی این رایانه</button>
      </div>`;

    let issueCard = '';
    if(info.can_issue){
      issueCard = `<div class="card">
          <div class="card-title">${ic('save')}صدور لایسنس جدید (ابزار فروشنده)</div>
          <p class="muted small">کلید خصوصی فقط در همین نسخهٔ مدیر است؛ لایسنس صادرشده را
             می‌توانید به‌عنوان فایل <code class="mono">.key</code> به مشتری بدهید.</p>
          <div class="row" style="margin-top:10px">
            <button class="btn primary" onclick="App.newLicense()">${ic('plus')}صدور لایسنس</button>
            <span class="muted small">کد این رایانه برای تست:</span>
            <span class="mono small">${esc(info.machine_code||'—')}</span>
          </div>
        </div>`;
    }

    let issuedCard = '';
    if(info.can_issue){
      const manage = (await api('license/manage')) || {};
      const issued = manage.issued || [];
      issuedCard = `<div class="card">
          <div class="card-title">${ic('audit')}لایسنس‌های صادرشده</div>
          ${table([
            {title:'شناسه', render:r=>`<b class="mono">${esc(r.lic_id||'')}</b>`},
            {title:'مشتری', render:r=>esc(r.customer||'')},
            {title:'نسخه', render:r=>r.edition==='premium'?'<span class="badge info">پرمیوم</span>':'<span class="badge neutral">پایه</span>'},
            {title:'کاربران', key:'seats'},
            {title:'دستگاه', render:r=>r.machine && r.machine!=='*'
                ? `<span class="mono small">${esc(r.machine.slice(0,8))}…</span>`
                : '<span class="badge neutral">آزاد</span>'},
            {title:'صدور', key:'issued'},
            {title:'انقضا', render:r=>esc(r.expires||'—')},
            {title:'عملیات', render:r=>`<a class="btn small" href="/api/license/issued/${r.id}">دانلود</a>
              <button class="btn small danger" onclick="App.delLicense(${r.id})">حذف</button>`},
          ], issued, {compact:true, empty:'هنوز لایسنسی صادر نشده است'})}
        </div>`;
    }

    const cloudData = (await this.loadCloud().catch(() => null)) || this._cloud || {};
    const cloud = cloudData.cloud || {};
    const adminPanel = !!cloudData.admin_panel;
    const requestsCard = adminPanel ? this.requestsCard() : '';
    /* نشانی سرور را اینستالر می‌نویسد؛ این دکمه فقط برای فروشنده است تا بدون
       نصب دوباره بتواند آن را عوض کند. */
    const showServerCfg = !!(cloudData.mode === 'admin' && this.meta &&
      this.meta.user && this.meta.user.role === 'admin');
    const cloudCard = `<div class="card">
        <div class="card-title">${ic('refresh')}لایسنس آنلاین
          ${cloud.configured ? '<span class="badge ok">متصل به سرور فروشنده</span>'
                             : '<span class="badge neutral">بدون سرور</span>'}</div>
        <p class="muted small" style="margin-top:6px">وضعیت ارتباط این برنامه با سرور
           فروشنده. نشانی سرور هنگام نصب نوشته می‌شود${showServerCfg
             ? ' و از همین صفحه هم قابل تغییر است' : ''}.</p>
        <div class="grid cols-2" style="margin-top:12px">
          <div class="stack">
            ${rowsOf([
              ['وضعیت', esc(this.CLOUD_LABELS[cloud.status] || cloud.status || '—')],
              ['زمان آخرین بررسی', esc(cloud.checked_at || '—')],
              ['شناسهٔ لایسنس سرور', `<span class="mono small">${esc(cloud.lic_id || '—')}</span>`],
            ])}
          </div>
          <div class="stack">
            ${rowsOf([
              ['شمارهٔ درخواست', cloud.request_id ? '#' + esc(String(cloud.request_id)) : '—'],
              ['مهلت بی‌اتصال', esc(String(cloud.grace || 15)) + ' روز'],
              ['فاصلهٔ بررسی', 'هر ' + esc(String(cloud.hours || 6)) + ' ساعت'],
            ])}
          </div>
        </div>
        ${info.online ? `<div class="hint" style="margin-top:10px"><span class="ico">${ic('info')}</span>
          <span>این لایسنس آنلاین است؛ اگر بیش از مهلت بالا به اینترنت وصل نشوید،
          برنامه تا نخستین بررسی قفل می‌ماند.</span></div>` : ''}
        ${cloud.error ? `<div class="hint bad" style="margin-top:10px">
          <span class="ico">${ic('warning')}</span><span>${esc(cloud.error)}</span></div>` : ''}
        <div class="row" style="margin-top:12px">
          <button class="btn" onclick="App.cloudPollHere()">${ic('refresh')}بررسی فوری لایسنس</button>
          <button class="btn" onclick="App.cloudRequestModal()">
            ${ic('upload')}درخواست صدور / تمدید</button>
          ${showServerCfg ? `<button class="btn" onclick="App.cloudServerModal()">
            ${ic('settings')}${cloud.configured ? 'تغییر نشانی سرور' : 'تنظیم نشانی سرور'}</button>` : ''}
        </div>
        ${!cloud.configured && showServerCfg ? `<div class="hint warn" style="margin-top:10px">
          <span class="ico">${ic('warning')}</span><span>تا وقتی نشانی سرور خالی است،
          «درخواست صدور / تمدید» و فهرست درخواست‌ها کار نمی‌کنند.</span></div>` : ''}
      </div>`;

    $('#content').innerHTML = this.dwrap('وضعیت لایسنس', '',
      `<div class="stack">${infoCard}${cloudCard}${requestsCard}${featureCard}${activateCard}${issueCard}${issuedCard}</div>`);
    if(adminPanel) this.loadRequests();
  },

  /* -------------------- درخواست‌های لایسنس (پنل فروشنده) ------------------- */
  /* فروشنده همین درخواست‌ها را در بات بله هم می‌بیند؛ تأیید از هر طرف که
     انجام شود، در سرور یکی می‌شود و برنامهٔ مشتری خودکار فعال می‌گردد. */
  requestsCard(adminPanel){
    return `<div class="card">
        <div class="card-head">
          <div class="card-title">${ic('inbox')}درخواست‌های لایسنس (از برنامه یا بات)
            <span class="badge neutral" id="reqCount">—</span></div>
          <div class="row">
            <button class="btn small" onclick="App.loadRequests()">
              ${ic('refresh')}به‌روزرسانی</button>
            <button class="btn small" onclick="App.helpDecide()">${ic('info')}راهنما</button>
          </div>
        </div>
        <p class="muted small">با «تأیید» تعداد کاربر و مدت (روز) را انتخاب می‌کنید؛
           لایسنس همان‌جا صادر می‌شود و برای مشتری می‌رود.</p>
        <div id="reqList" class="stack" style="margin-top:12px">
          <div class="empty"><span class="skel" style="width:100%"></span></div>
        </div>
      </div>`;
  },

  async helpDecide(){
    modal('تأیید یا رد درخواست', `
      <div class="hint"><span class="ico">${ic('info')}</span><span>
        هر درخواست هم در این برنامه و هم در بات بله دیده می‌شود؛ تأیید از هر
        طرفی که انجام شود در سرور یکی می‌شود. با تأیید، <b>تعداد کاربر</b> و
        <b>مدت به روز</b> را انتخاب می‌کنید و لایسنس همان لحظه صادر و برای مشتری
        فرستاده می‌شود؛ برنامهٔ او خودکار فعال می‌گردد.
      </span></div>
      <p class="muted small">«توضیح مشتری» یادداشتی است که خود مشتری فقط در همین درخواست نوشته است.</p>`,
      `<button class="btn" onclick="App.closeModal()">بستن</button>`);
  },

  async loadRequests(){
    const box = $('#reqList');
    if(!box) return;
    const d = await apiTry('license/requests');
    if(d === null) return;
    this._reqMeta = d;
    this.renderRequests(d.requests || []);
  },

  renderRequests(list){
    const box = $('#reqList');
    if(!box) return;
    const badge = $('#reqCount');
    if(badge){
      badge.textContent = list.length ? (list.length + ' در انتظار') : 'موردی نیست';
      badge.className = 'badge ' + (list.length ? 'warn' : 'ok');
    }
    if(!list.length){
      box.innerHTML = emptyState('درخواستی در انتظار تأیید نیست',
        'هر درخواست تازهٔ مشتری، همین‌جا و در بات بله می‌آید.');
      return;
    }
    box.innerHTML = list.map(r => `
      <div class="card card-anim" style="margin:0;background:var(--muted)">
        <div class="card-head" style="margin-bottom:8px">
          <div class="card-title">${ic('inbox')}درخواست #${r.id}
            <span class="badge neutral">${esc(r.created_at || '')}</span></div>
          <div class="row">
            <button class="btn small primary" onclick="App.approveRequest(${r.id})">
              ${ic('check')}تأیید</button>
            <button class="btn small danger" onclick="App.denyRequest(${r.id})">
              ${ic('close')}رد</button>
          </div>
        </div>
        <div class="grid cols-2">
          <div class="stack">${rowsOf([
            ['مشتری', esc(r.customer || '—')],
            ['تلفن', esc(r.phone || '—')],
          ])}</div>
          <div class="stack">${rowsOf([
            ['کد رایانه', `<span class="mono small">${esc(r.machine_code || '—')}</span>`],
            ['دستگاه‌های فعال', esc(String(r.devices_active || 0)) +
              (r.devices_max ? ' از ' + esc(String(r.devices_max)) : '')],
          ])}</div>
        </div>
        ${r.note ? `<div class="hint" style="margin-top:10px">
          <span class="ico">${ic('notes')}</span>
          <span>توضیح مشتری: ${esc(r.note)}</span></div>` : ''}
      </div>`).join('');
  },

  approveRequest(id){
    const d = this._reqMeta || {};
    const editions = d.editions && d.editions.length ? d.editions
      : [{id:'premium', label:'پرمیوم'}, {id:'base', label:'پایه'}];
    const dayChoices = (d.days_choices && d.days_choices.length)
      ? d.days_choices : [30, 90, 180, 365, 0];
    modalForm('تأیید درخواست #' + id, [
      {name:'ed_edition', label:'نسخهٔ لایسنس', type:'select',
       value: d.default_edition || 'premium',
       options: editions.map(e => ({value: e.id, label: e.label}))},
      {name:'ed_seats', label:'تعداد کاربر مجاز', type:'number',
       value: d.default_seats || 3},
      {name:'ed_days', label:'مدت اعتبار', type:'select',
       value: String(d.default_days == null ? 365 : d.default_days),
       options: dayChoices.map(x => ({value: String(x),
         label: x ? (x + ' روز') : 'بدون انقضا'}))},
      {name:'ed_note', label:'توضیح برای مشتری (اختیاری)', type:'textarea', value:''},
    ], null,
    `<button class="btn primary" onclick="App.doDecide(${id}, 'approve')">
       ${ic('check')}تأیید و صدور لایسنس</button>
     <button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },

  denyRequest(id){
    modalForm('رد درخواست #' + id, [
      {name:'ed_note', label:'دلیل رد (اختیاری)', type:'textarea', value:''},
    ], null,
    `<button class="btn danger" onclick="App.doDecide(${id}, 'deny')">
       ${ic('close')}رد درخواست</button>
     <button class="btn" onclick="App.closeModal()">انصراف</button>`,
    {grid:'c2'});
  },

  async doDecide(id, action){
    const body = {action: action, note: fieldVal('ed_note')};
    if(action === 'approve'){
      body.edition = fieldVal('ed_edition');
      body.seats = Number(fieldVal('ed_seats')) || 0;
      body.days = fieldVal('ed_days');
    }
    const d = await apiTry('license/requests/' + id + '/decide',
      {method:'POST', body:body});
    if(d === null) return;
    this.closeModal();
    toast(d.message || (action === 'approve' ? 'لایسنس صادر شد' : 'درخواست رد شد'),
          action === 'approve' ? 'ok' : 'info');
    if(this.route === 'license') this.v_license(); else this.navigate('license');
  },

  /* ------------- درخواست از داخل برنامه (صفحهٔ فعال‌سازی/حساب) ------------- */
  cloudRequestModal(){
    const s = (this.meta && this.meta.settings) || {};
    modalForm('درخواست صدور / تمدید لایسنس', [
      {name:'cr_name', label:'نام فروشگاه / مشتری', value: s.company_name || ''},
      {name:'cr_phone', label:'شمارهٔ تماس', value: s.company_phone || ''},
      {name:'cr_note', label:'توضیح برای فروشنده (اختیاری)', type:'textarea', value:''},
    ], null,
    `<button class="btn primary" onclick="App.submitCloudRequest()">
       ${ic('upload')}ارسال درخواست</button>
     <button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },

  async submitCloudRequest(){
    const name = fieldVal('cr_name'), phone = fieldVal('cr_phone');
    const note = fieldVal('cr_note');
    const d = await apiTry('license/cloud/request', {method:'POST',
      body:{name:name.trim(), phone:phone.trim(), note:note.trim()}});
    if(d === null) return;
    this.closeModal();
    this._cloud = {cloud:d.cloud, license:d.license};
    toast(d.message || 'درخواست ثبت شد','ok');
    if(this.route === 'license') this.v_license(); else this.navigate('license');
    this.startCloudWatch();
  },

  /* ------------------------------ حساب کاربری ----------------------------- */
  async v_account(){
    const me = (this.meta && this.meta.user) || {};
    const lic = (this.meta && this.meta.license) || {};
    const s = (this.meta && this.meta.settings) || {};
    const cloudData = (await this.loadCloud().catch(() => null)) || this._cloud || {};
    const cloud = cloudData.cloud || {};

    const meCard = `<div class="card">
        <div class="card-title">${ic('user')}حساب کاربری من</div>
        <div class="grid cols-2" style="margin-top:12px">
          <div class="stack">${rowsOf([
            ['نام کاربری', `<span class="mono small">${esc(me.username || '—')}</span>`],
            ['نام و نام خانوادگی', esc(me.full_name || '—')],
          ])}</div>
          <div class="stack">${rowsOf([
            ['نقش', esc(me.role === 'admin' ? 'مدیر سیستم' : 'کاربر')],
            ['نسخهٔ برنامه', esc(lic.mode === 'admin' ? 'نسخهٔ فروشنده' : 'نسخهٔ مشتری')],
          ])}</div>
        </div>
        <div class="row" style="margin-top:12px">
          <button class="btn" onclick="App.changePass()">${ic('lock')}تغییر گذرواژه</button>
        </div>
      </div>`;

    const licCard = `<div class="card">
        <div class="card-title">${ic('lock')}لایسنس این رایانه
          ${lic.valid ? '<span class="badge ok">فعال</span>'
                      : '<span class="badge bad">غیرفعال</span>'}</div>
        <div class="grid cols-2" style="margin-top:12px">
          <div class="stack">${rowsOf([
            ['نسخه', esc(lic.edition === 'premium' ? 'پرمیوم' : (lic.edition || '—'))],
            ['کاربران مجاز', esc(String(lic.seats || 1))],
            ['کد این رایانه', `<span class="mono small">${esc(lic.machine_code || '—')}</span>`],
          ])}</div>
          <div class="stack">${rowsOf([
            ['تاریخ انقضا', esc(lic.expires || 'بدون انقضا')],
            ['روز باقی‌مانده', (typeof lic.days_left === 'number')
              ? esc(String(lic.days_left)) : '—'],
            ['وضعیت بررسی آنلاین',
              esc(this.CLOUD_LABELS[cloud.status] || cloud.status || '—')],
          ])}</div>
        </div>
        ${lic.message ? `<div class="hint" style="margin-top:10px">
          <span class="ico">${ic('info')}</span><span>${esc(lic.message)}</span></div>` : ''}
      </div>`;

    const badge = cloud.status === 'pending' ? 'warn'
      : (cloud.status === 'active' ? 'ok' : (cloud.status ? 'bad' : 'neutral'));
    const reqCard = !cloud.configured ? this.noServerCard() : `<div class="card">
        <div class="card-title">${ic('upload')}درخواست صدور / تمدید لایسنس
          ${cloud.status ? `<span class="badge ${badge}">${esc(this.CLOUD_LABELS[cloud.status] || cloud.status)}</span>` : ''}</div>
        <p class="muted small">درخواست شما هم برای برنامهٔ فروشنده و هم در بات بله
           می‌رود. فروشنده با انتخاب <b>تعداد کاربر</b> و <b>تعداد روز</b> تأیید
           می‌کند و لایسنس خودکار نصب می‌شود.</p>
        <div class="form-grid c2">
          <div class="field"><label for="accName">نام فروشگاه / مشتری</label>
            <input id="accName" value="${esc(s.company_name || '')}"></div>
          <div class="field"><label for="accPhone">شمارهٔ تماس</label>
            <input id="accPhone" inputmode="tel" value="${esc(s.company_phone || '')}"></div>
          <div class="field" style="grid-column:1 / -1">
            <label for="accNote">توضیح برای فروشنده (اختیاری)</label>
            <textarea id="accNote" rows="2" maxlength="200"
              placeholder="مثلاً: سه شعبه داریم یا لایسنس را تمدید کنید"></textarea></div>
        </div>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" onclick="App.sendAccountRequest()">
            ${ic('upload')}ارسال درخواست</button>
          <button class="btn" onclick="App.cloudPollHere()">
            ${ic('refresh')}بررسی وضعیت لایسنس</button>
          <button class="btn" onclick="App.helpDecide()">${ic('info')}چه اتفاقی می‌افتد؟</button>
        </div>
        ${cloud.request_id ? `<p class="muted small" style="margin-top:10px">
          آخرین درخواست: <b class="mono">#${esc(String(cloud.request_id))}</b>
          ${cloud.checked_at ? '— آخرین بررسی: ' + esc(cloud.checked_at) : ''}
          ${cloud.message ? '— ' + esc(cloud.message) : ''}</p>` : ''}
        ${cloud.error ? `<div class="hint bad" style="margin-top:10px">
          <span class="ico">${ic('warning')}</span><span>${esc(cloud.error)}</span></div>` : ''}
      </div>`;

    $('#content').innerHTML = this.dwrap('حساب کاربری و لایسنس', '',
      `<div class="stack">${meCard}${licCard}${reqCard}</div>`);
    if(cloud.status === 'pending') this.startCloudWatch();
  },

  /* این نصب به سرور فروشنده وصل نیست: جای فرم درخواست آنلاین، راه درست را
     نشان می‌دهیم تا کاربر پیام خطای بی‌سرانجام نگیرد. */
  noServerCard(){
    return `<div class="card">
        <div class="card-title">${ic('upload')}درخواست صدور / تمدید لایسنس
          <span class="badge neutral">بدون اتصال</span></div>
        <div class="hint warn" style="margin-top:10px">
          <span class="ico">${ic('warning')}</span><span>این نصب به سرور فروشنده وصل
          نیست، پس درخواست آنلاین فرستاده نمی‌شود. لایسنس را از فروشنده بگیرید و
          در صفحهٔ «وضعیت لایسنس» وارد کنید.</span></div>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" onclick="App.navigate('license')">
            ${ic('lock')}وارد کردن متن لایسنس</button>
          <button class="btn" onclick="App.helpDecide()">${ic('info')}چه اتفاقی می‌افتد؟</button>
        </div>
      </div>`;
  },

  /* نشانی سرور لایسنس (نسخهٔ فروشنده): هم برای بار اول و هم برای تغییر بعدی. */
  cloudServerModal(){
    const c = (this._cloud || {}).cloud || {};
    modalForm('نشانی سرور لایسنس', [
      {name:'cs_server', label:'نشانی سرور (مثل https://license.example.com)',
       value: c.server || '', placeholder:'https://…'},
      {name:'cs_token', label:'کلید اتصال برنامه (اختیاری؛ اگر فروشنده داده است)',
       value:''},
    ], null,
    `<button class="btn primary" onclick="App.saveCloudServer()">
       ${ic('save')}ذخیره</button>
     <button class="btn" onclick="App.closeModal()">انصراف</button>`,
    {wide:true});
  },

  async saveCloudServer(){
    const server = fieldVal('cs_server').trim().replace(/\/+$/, '');
    const token = fieldVal('cs_token').trim();
    if(server && !/^https?:\/\//i.test(server)){
      toast('نشانی باید با http:// یا https:// شروع شود','error'); return;
    }
    const body = {license_server: server};
    if(token) body.license_client_token = token;
    const d = await apiTry('license/cloud/settings', {method:'POST', body});
    if(d === null) return;
    this.closeModal();
    this._cloud = {cloud: d.cloud, license: d.license};
    toast(d.message || 'نشانی سرور ذخیره شد','ok');
    this.v_license();
  },

  async sendAccountRequest(){
    const name = ($('#accName') || {}).value || '';
    const phone = ($('#accPhone') || {}).value || '';
    const note = ($('#accNote') || {}).value || '';
    const d = await apiTry('license/cloud/request', {method:'POST',
      body:{name:name.trim(), phone:phone.trim(), note:note.trim()}});
    if(d === null) return;
    this._cloud = {cloud:d.cloud, license:d.license};
    toast(d.message || 'درخواست ثبت شد','ok');
    this.v_account();
    this.startCloudWatch();
  },

  async activateHere(){
    const text = ($('#licKeyNew').value || '').trim();
    if(!text){ toast('متن لایسنس را وارد کنید','error'); return; }
    const r = await apiTry('license/activate', {method:'POST', body:{key:text}});
    if(r!==null){ toast('لایسنس فعال شد','ok'); this.meta.license = r; this.navigate('license'); }
  },

  newLicense(){
    const opts = Object.keys(FEATURE_LABELS).map(k =>
      ({value:k, label:FEATURE_LABELS[k]}));
    modal('صدور لایسنس جدید',
      `<div class="form-grid c2">
         ${field({name:'l_customer', label:'نام مشتری', required:true})}
         ${field({name:'l_edition', label:'نسخه', type:'select', value:'premium',
                  options:[{value:'premium',label:'پرمیوم (همهٔ قابلیت‌ها)'},
                           {value:'base',label:'پایه'}]})}
         ${field({name:'l_seats', label:'تعداد کاربران', type:'number', value:1})}
         ${field({name:'l_months', label:'مدت اعتبار (ماه؛ ۰ = بدون انقضا)', type:'select',
                  value:'12', options:[{value:'0',label:'بدون انقضا'},{value:'1',label:'۱ ماه'},
                  {value:'3',label:'۳ ماه'},{value:'6',label:'۶ ماه'},{value:'12',label:'۱ سال'},
                  {value:'24',label:'۲ سال'},{value:'36',label:'۳ سال'}]})}
         ${field({name:'l_machine', label:'کد دستگاه مشتری (خالی = آزاد)'})}
         ${field({name:'l_note', label:'یادداشت'})}
       </div>
       <div class="field"><label>قابلیت‌ها</label>
         <div class="perm-grid">
           ${opts.map(o => `<label><input type="checkbox" class="lic-feat" value="${o.value}" checked>
             <span>${esc(o.label)}</span></label>`).join('')}
         </div></div>`,
      `<button class="btn primary" onclick="App.issueLicense()">صدور لایسنس</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`);
    const ed = document.getElementById('f_l_edition');
    if(ed) ed.addEventListener('change', () => {
      const premium = ed.value === 'premium';
      $$('.lic-feat').forEach(c => { c.checked = premium; c.disabled = !premium; });
      const seats = document.getElementById('f_l_seats');
      if(seats) seats.value = premium ? 3 : 1;
    });
  },

  async issueLicense(){
    const feats = $$('.lic-feat').filter(c => c.checked).map(c => c.value);
    const d = {
      customer: fieldVal('l_customer'), edition: fieldVal('l_edition'),
      seats: Number(fieldVal('l_seats') || 1), months: Number(fieldVal('l_months') || 12),
      machine: fieldVal('l_machine'), note: fieldVal('l_note'), features: feats,
    };
    const r = await apiTry('license/issue', {method:'POST', body:d});
    if(r === null) return;
    this._issuedKey = r;
    this.closeModal();
    modal('لایسنس صادر شد',
      `<div class="stack">
         <div class="row"><span class="muted small">شناسه:</span><b class="mono">${esc(r.lic_id||'')}</b>
           <span class="muted small">مشتری:</span><b>${esc(r.payload.customer||'')}</b></div>
         <div class="row"><span class="muted small">انقضا:</span><b>${esc(r.payload.expires||'بدون انقضا')}</b></div>
         <div class="license-key">${esc(r.key||'')}</div>
         <div class="row">
           <button class="btn primary" onclick="App.copyKey()">کپی متن لایسنس</button>
           <button class="btn" onclick="App.saveKeyFile()">ذخیرهٔ فایل .key</button>
         </div>
         <div class="hint"><span class="ico">${ic('info')}</span><span>این متن یا فایل را به مشتری بدهید؛
           او آن را در صفحهٔ «فعال‌سازی» وارد می‌کند.</span></div>
       </div>`, `<button class="btn" onclick="App.closeModal();App.navigate('license')">بستن</button>`, true);
  },

  copyKey(){
    const k = (this._issuedKey && this._issuedKey.key) || '';
    if(navigator.clipboard && navigator.clipboard.writeText)
      navigator.clipboard.writeText(k).then(() => toast('متن لایسنس کپی شد','ok'),
        () => toast('کپی نشد؛ متن را دستی انتخاب کنید','error'));
    else toast('متن را دستی انتخاب و کپی کنید','info');
  },

  saveKeyFile(){
    const it = this._issuedKey || {};
    const name = (it.lic_id || 'license') + '.key';
    const blob = new Blob([it.file || ''], {type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  },

  async delLicense(id){ if(!confirm('این رکورد لایسنس حذف شود؟')) return;
    await apiTry('license/issued/'+id, {method:'DELETE'}); this.navigate('license'); },

  /* -------------------------------- سیستم -------------------------------- */
  async v_systemusers(){
    const res = await api('users');
    const rows = res || [];
    const cols = [
      {title:'نام کاربری', render:r=>`<b>${esc(r.username)}</b>`},
      {title:'نام کامل', key:'full_name'},
      {title:'نقش', render:r=>r.role==='admin'?'<span class="badge info">مدیر</span>':'<span class="badge neutral">کاربر</span>'},
      {title:'دسترسی‌ها', render:r=>r.role==='admin'
          ? '<span class="muted small">همه</span>'
          : (r.perms && r.perms.length
              ? `<span class="muted small">${r.perms.map(p=>esc(PERM_LABELS[p]||p)).join('، ')}</span>`
              : '<span class="muted small">پیش‌فرض</span>')},
      {title:'آخرین ورود', render:r=>esc(r.last_login||'—')},
      {title:'وضعیت', render:r=>{
          const bits = [];
          bits.push(r.active ? '<span class="badge ok">فعال</span>'
                             : '<span class="badge bad">غیرفعال</span>');
          if(r.locked) bits.push('<span class="badge warn">قفل موقت</span>');
          return bits.join(' ');
        }},
      {title:'عملیات', render:r=>{
          const a = [``];
          a.push(`<button class="btn small" onclick="App.editUser(${r.id})">ویرایش</button>`);
          if(r.locked) a.push(`<button class="btn small" onclick="App.unlockUser(${r.id})">بازکردن قفل</button>`);
          if(r.id !== 1) a.push(`<button class="btn small danger" onclick="App.delUser(${r.id})">حذف</button>`);
          return a.join(' ');
        }},
    ];
    $('#content').innerHTML = this.dwrap('کاربران سیستم',
      `<button class="btn primary" onclick="App.newUser()">${ic('plus')}کاربر جدید</button>`,
      this.seatsInfo() +
      '<div class="card">' + table(cols, rows, {compact:true}) + '</div>');
  },

  /* مصرف سهم کاربران از لایسنس */
  seatsInfo(){
    const lic = (this.meta && this.meta.license) || {};
    const max = Number(lic.seats || 1);
    if(!this.isAdmin()) return '';
    const cls = this.hasFeature('more_users') && lic.valid ? 'hint' : 'hint warn';
    return `<div class="${cls}" style="margin-bottom:12px">
      <span class="ico">${ic('users')}</span>
      <span>سقف کاربران این لایسنس: <b>${esc(String(max))} نفر</b>` +
      (this.hasFeature('more_users') ? '' : ' — افزودن کاربر بیشتر نیازمند نسخهٔ پرمیوم است.') +
      `</span></div>`;
  },

  userPermsHtml(selected){
    selected = selected || [];
    return `<div class="field"><label>دسترسی به بخش‌های برنامه</label>
      <div class="perm-grid">${Object.keys(PERM_LABELS).map(k =>
        `<label><input type="checkbox" class="u-perm" value="${k}"` +
        (selected.indexOf(k) !== -1 ? ' checked' : '') +
        `><span>${esc(PERM_LABELS[k])}</span></label>`).join('')}</div>
      <p class="hint-text">اگر هیچ‌کدام انتخاب نشود، کاربر به بخش‌های پیش‌فرض دسترسی دارد.</p></div>`;
  },

  newUser(){
    modal('کاربر جدید',
      `<div class="form-grid c2">
         ${field({name:'u_username', label:'نام کاربری', required:true})}
         ${field({name:'u_password', label:'گذرواژه', type:'password', required:true})}
         ${field({name:'u_fullname', label:'نام کامل'})}
         ${field({name:'u_phone', label:'تلفن'})}
         ${field({name:'u_email', label:'ایمیل'})}
         ${field({name:'u_role', label:'نقش', type:'select', value:'user',
                  options:[{value:'user',label:'کاربر'},{value:'admin',label:'مدیر سیستم'}]})}
       </div>${this.userPermsHtml(Object.keys(PERM_LABELS))}`,
      `<button class="btn primary" onclick="App.saveUser()">ذخیره</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },

  async saveUser(){
    const d = {username:fieldVal('u_username'), password:fieldVal('u_password'),
      full_name:fieldVal('u_fullname'), phone:fieldVal('u_phone'), email:fieldVal('u_email'),
      role:fieldVal('u_role'), perms: this._checkedPerms()};
    const r = await apiTry('users', {method:'POST', body:d});
    if(r!==null){ this.closeModal(); toast('کاربر ایجاد شد','ok'); this.navigate('system-users'); }
  },

  _checkedPerms(){ return $$('.u-perm').filter(c => c.checked).map(c => c.value); },

  async editUser(id){
    const rows = (await api('users')) || [];
    const u = rows.filter(r => r.id === id)[0];
    if(!u){ toast('کاربر یافت نشد','error'); return; }
    modal('ویرایش کاربر: ' + u.username,
      `<div class="form-grid c2">
         ${field({name:'ue_full', label:'نام کامل', value:u.full_name||''})}
         ${field({name:'ue_phone', label:'تلفن', value:u.phone||''})}
         ${field({name:'ue_email', label:'ایمیل', value:u.email||''})}
         ${field({name:'ue_pass', label:'گذرواژه جدید (خالی = بدون تغییر)', type:'password'})}
         ${field({name:'ue_role', label:'نقش', type:'select', value:u.role,
                  options:[{value:'user',label:'کاربر'},{value:'admin',label:'مدیر سیستم'}]})}
         ${field({name:'ue_active', label:'وضعیت حساب', type:'select',
                  value:u.active?'1':'0', options:[{value:'1',label:'فعال'},{value:'0',label:'غیرفعال'}]})}
         ${field({name:'ue_note', label:'یادداشت', value:u.note||''})}
       </div>${this.userPermsHtml(u.perms || [])}`,
      `<button class="btn primary" onclick="App.doEditUser(${id})">ذخیره</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },

  async doEditUser(id){
    const d = {full_name:fieldVal('ue_full'), phone:fieldVal('ue_phone'),
      email:fieldVal('ue_email'), role:fieldVal('ue_role'), note:fieldVal('ue_note'),
      active: fieldVal('ue_active') === '1', perms: this._checkedPerms()};
    if(fieldVal('ue_pass')) d.password = fieldVal('ue_pass');
    const r = await apiTry('users/'+id, {method:'PUT', body:d});
    if(r!==null){ this.closeModal(); toast('کاربر ویرایش شد','ok'); this.navigate('system-users'); }
  },

  async unlockUser(id){ await apiTry('users/'+id, {method:'PUT', body:{unlock:true}});
    toast('قفل ورود این کاربر باز شد','ok'); this.navigate('system-users'); },

  async delUser(id){ if(!confirm('کاربر حذف شود؟')) return;
    await apiTry('users/'+id,{method:'DELETE'}); this.navigate('system-users'); },

  async v_systemactivity(){
    const rows = await api('activity');
    $('#content').innerHTML = this.dwrap('گردش فعالیت کاربران', '', `<div class="card">${table([
      {title:'زمان', key:'at'}, {title:'کاربر', render:r=>esc(r.username||'')},
      {title:'عملیات', key:'action'}, {title:'جزئیات', render:r=>esc(r.detail||'')},
    ], rows)}</div>`);
  },
  async v_systemaudit(){
    const rows = await api('audit');
    $('#content').innerHTML = this.dwrap('گزارش اصلاح و حذف (ردیابی)', '', `<div class="card">${table([
      {title:'زمان', key:'at'}, {title:'کاربر', render:r=>esc(r.username||'')},
      {title:'عملیات', render:r=>`<span class="badge warn">${esc(r.action)}</span>`},
      {title:'موضوع', render:r=>esc(r.entity||'')}, {title:'شناسه', render:r=>r.entity_id||''},
      {title:'جزئیات', render:r=>esc(r.detail||'')},
    ], rows)}</div>`);
  },
  async v_systemnotes(){
    const rows = await api('notes');
    const cols = [
      {title:'عنوان', render:r=>`<b>${esc(r.title||'')}</b>`},
      {title:'متن', render:r=>esc(r.body||'')},
      {title:'یادآور', render:r=>esc(r.remind_at||'—')},
      {title:'وضعیت', render:r=>r.done?'<span class="badge ok">انجام‌شده</span>':'<span class="badge warn">در جریان</span>'},
      {title:'عملیات', render:r=>`${r.done?'':`<button class="btn small" onclick="App.noteDone(${r.id})">انجام شد</button>`}
        <button class="btn small danger" onclick="App.delNote(${r.id})">حذف</button>`},
    ];
    $('#content').innerHTML = this.dwrap('یادداشت و یادآور', `<button class="btn primary" onclick="App.newNote()">+ یادداشت جدید</button>`,
      `<div class="card">${table(cols, rows, {empty:'یادداشتی ثبت نشده است'})}</div>`);
  },
  newNote(){ modalForm('یادداشت جدید', [{name:'n_title', label:'عنوان'},
      {name:'n_body', label:'متن یادداشت', type:'textarea'},
      {name:'n_remind', label:'تاریخ یادآور (اختیاری)', type:'date', value:''}], null,
    `<button class="btn primary" onclick="App.saveNote()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`); },
  async saveNote(){ const r = await apiTry('notes', {method:'POST', body:{title:fieldVal('n_title'), body:fieldVal('n_body'), remind_at:fieldVal('n_remind')}});
    if(r!==null){ this.closeModal(); this.navigate('system-notes'); } },
  async noteDone(id){ await apiTry('notes/'+id, {method:'PUT', body:{done:1}}); this.navigate('system-notes'); },
  async delNote(id){ await apiTry('notes/'+id, {method:'DELETE'}); this.navigate('system-notes'); },

  /* ------------------------------ پشتیبان‌گیری ----------------------------- */
  fmtSize(n){
    n = Number(n) || 0;
    if(n < 1024) return n + ' بایت';
    if(n < 1024 * 1024) return (n / 1024).toFixed(1) + ' کیلوبایت';
    return (n / 1024 / 1024).toFixed(1) + ' مگابایت';
  },

  bkName(name){ return String(name || '').replace(/[^A-Za-z0-9._-]/g, ''); },

  async v_systembackup(){
    const b = await api('backups');
    const files = (b && b.files) || [];
    const auto = String((b && b.auto) || '1') === '1';
    const cols = [
      {title:'فایل', render:r=>`<span class="mono small">${esc(r.name)}</span>`},
      {title:'نوع', render:r=>r.kind === 'auto'
        ? '<span class="badge info">خودکار</span>'
        : (r.kind === 'safety' ? '<span class="badge warn">قبل از بازگردانی</span>'
                               : '<span class="badge neutral">دستی</span>')},
      {title:'تاریخ', render:r=>esc(r.at || '—')},
      {title:'حجم', render:r=>esc(this.fmtSize(r.size))},
      {title:'عملیات', render:r=>{
        const n = this.bkName(r.name);
        return `<a class="btn small" href="/api/backups/${n}">${ic('download')}دانلود</a>
          <button class="btn small" onclick="App.restoreBackup('${n}')">${ic('upload')}بازگردانی</button>
          <button class="btn small danger" onclick="App.delBackup('${n}')">${ic('trash')}حذف</button>`;
      }},
    ];
    $('#content').innerHTML = this.dwrap('پشتیبان‌گیری و بازیابی',
      `<button class="btn primary" onclick="App.newBackup()">${ic('backup')}ساخت پشتیبان تازه</button>`,
      `<div class="card">
        <div class="card-title">${ic('settings')}تنظیمات پشتیبان‌گیری</div>
        <div class="grid cols-2" style="margin-top:12px">
          <div class="stack">
            <div class="row"><span class="muted small">پوشهٔ پشتیبان‌ها</span>
              <b class="mono small">${esc((b && b.dir) || '—')}</b></div>
            <button class="btn small" onclick="App.backupDirChange()">تغییر پوشه</button>
          </div>
          <div class="stack">
            <div class="row"><span class="muted small">پشتیبان خودکار هنگام باز شدن برنامه</span>
              <b>${auto ? 'فعال' : 'غیرفعال'}</b></div>
            <div class="row"><span class="muted small">تعداد نسخه‌های نگه‌داشته‌شده</span>
              <b>${esc(String((b && b.keep) || 20))}</b></div>
            <div class="row">
              <button class="btn small" onclick="App.backupToggleAuto(${auto ? 'false' : 'true'})">
                ${auto ? 'خاموش کردن پشتیبان خودکار' : 'روشن کردن پشتیبان خودکار'}</button>
              <button class="btn small" onclick="App.backupKeep()">تغییر تعداد نگهداری</button>
            </div>
          </div>
        </div>
      </div>
      <div class="card"><div class="card-title">${ic('backup')}نسخه‌های پشتیبان (${files.length})</div>
        ${table(cols, files, {compact:true,
          empty:'هنوز پشتیبانی ساخته نشده است',
          emptyAction:'ساخت پشتیبان',
          emptyActionJs:'App.newBackup()'})}
      </div>
      <div class="grid cols-2">
        <div class="card"><div class="card-title">دانلود یک فایل پشتیبان</div>
          <p class="muted small">فایل پایگاه‌دادهٔ کامل را برای نگه‌داری بیرون از برنامه دانلود کنید.</p>
          <a class="btn" href="/api/backup">${ic('download')}دانلود پشتیبان فوری</a></div>
        <div class="card"><div class="card-title">بازیابی از فایل بیرونی</div>
          <p class="muted small">فقط فایل پشتیبان این برنامه را انتخاب کنید. پس از بازیابی،
            برنامه را دوباره اجرا کنید.</p>
          <input type="file" id="restoreFile" accept=".db">
          <button class="btn danger" style="margin-top:10px" onclick="App.doRestore()">بازیابی</button></div>
      </div>
      <div class="card"><div class="card-title">خروجی اطلاعات (CSV برای اکسل)</div>
        <a class="btn" href="/api/export/parties">اشخاص</a>
        <a class="btn" href="/api/export/products">کالاها</a>
        <a class="btn" href="/api/export/invoices">فاکتورها</a>
        <a class="btn" href="/api/export/inventory">موجودی انبار</a></div>`);
  },

  async newBackup(){
    const r = await apiTry('backups', {method:'POST', body:{create:true}});
    if(r === null) return;
    toast('پشتیبان ساخته شد: ' + (r.created || ''),'ok');
    this.navigate('system-backup');
  },

  async backupToggleAuto(on){
    const r = await apiTry('backups', {method:'POST', body:{auto: !!on}});
    if(r === null) return;
    toast(on ? 'پشتیبان خودکار روشن شد' : 'پشتیبان خودکار خاموش شد','ok');
    this.navigate('system-backup');
  },

  backupKeep(){
    const keep = (this.meta.settings && this.meta.settings.backup_keep) || '20';
    modalForm('تعداد نسخه‌های پشتیبان', [
      {name:'bk_keep', label:'چند نسخهٔ تازه نگه داشته شود؟', type:'number',
       value: keep, required:true}], null,
      `<button class="btn primary" onclick="App.saveBackupKeep()">ذخیره</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },

  async saveBackupKeep(){
    const r = await apiTry('backups', {method:'POST', body:{keep: fieldVal('bk_keep')}});
    if(r === null) return;
    this.closeModal();
    toast('تنظیمات پشتیبان ذخیره شد','ok');
    this.navigate('system-backup');
  },

  backupDirChange(){
    modalForm('پوشهٔ پشتیبان‌ها', [
      {name:'bk_dir', label:'مسیر پوشه (روی همین رایانه)', required:true,
       value: (this._backupDir || '')}], null,
      `<button class="btn primary" onclick="App.saveBackupDir()">ذخیره</button>
       <button class="btn" onclick="App.closeModal()">انصراف</button>`);
  },

  async saveBackupDir(){
    const r = await apiTry('backups', {method:'POST', body:{dir: fieldVal('bk_dir')}});
    if(r === null) return;
    this._backupDir = r.dir;
    this.closeModal();
    toast('پوشهٔ پشتیبان تغییر کرد','ok');
    this.navigate('system-backup');
  },

  async restoreBackup(name){
    if(!confirm('اطلاعات فعلی با این نسخهٔ پشتیبان جایگزین شود؟\n' +
                '(از وضعیت فعلی هم یک نسخهٔ امن گرفته می‌شود.)')) return;
    const r = await apiTry('backups/restore', {method:'POST', body:{name: name}});
    if(r === null) return;
    toast('بازگردانی انجام شد؛ لطفاً برنامه را ببندید و دوباره اجرا کنید','ok');
  },

  async delBackup(name){
    if(!confirm('این فایل پشتیبان پاک شود؟')) return;
    const r = await apiTry('backups/' + this.bkName(name), {method:'DELETE'});
    if(r === null) return;
    toast('فایل پشتیبان پاک شد','ok');
    this.navigate('system-backup');
  },

  async doRestore(){
    const f = document.getElementById('restoreFile').files[0];
    if(!f){ toast('فایلی انتخاب نشده است','error'); return; }
    const fd = new FormData(); fd.append('file', f);
    const res = await fetch('/api/restore', {method:'POST', body:fd});
    const d = await res.json();
    if(d.ok) toast('بازیابی انجام شد؛ لطفاً برنامه را ببندید و دوباره اجرا کنید','ok');
    else toast(d.error||'خطا در بازیابی','error');
  },

  async v_systemsettings(){
    const s = this.meta.settings;
    const f = [
      {name:'company_name', label:'نام فروشگاه / شرکت', value:s.company_name||''},
      {name:'company_phone', label:'تلفن', value:s.company_phone||''},
      {name:'company_economic_code', label:'کد اقتصادی', value:s.company_economic_code||''},
      {name:'company_national_id', label:'شناسه/کد ملی', value:s.company_national_id||''},
      {name:'company_address', label:'نشانی', type:'textarea', value:s.company_address||''},
      {name:'currency', label:'واحد پول', value:s.currency||'ریال'},
      {name:'tax_rate', label:'نرخ مالیات پیش‌فرض (٪)', type:'number', value:s.tax_rate||9},
      {name:'tax_enabled', label:'احتساب مالیات بر ارزش افزوده', type:'select', value:s.tax_enabled===undefined?'1':String(s.tax_enabled), options:[{value:'1',label:'فعال'},{value:'0',label:'غیرفعال'}]},
      {name:'fiscal_year_start', label:'شروع سال مالی', type:'date', value:s.fiscal_year_start||this.meta.today},
      {name:'scrap_warehouse_id', label:'انبار پیش‌فرض ضایعات', type:'select', value:s.scrap_warehouse_id||'2', options:[]},
    ];
    $('#content').innerHTML = this.dwrap('تنظیمات برنامه', '',
      `<div class="card"><div class="form-grid c2">${f.map(x=>field(x)).join('')}</div>
        <div style="margin-top:14px"><button class="btn primary" onclick="App.saveSettings()">ذخیره تنظیمات</button>
        <button class="btn" onclick="App.changePass()">تغییر گذرواژه من</button></div></div>`);
    document.getElementById('f_scrap_warehouse_id').innerHTML = this.optWarehouses(s.scrap_warehouse_id);
  },
  async saveSettings(){
    const keys = ['company_name','company_phone','company_economic_code','company_national_id',
      'company_address','currency','tax_rate','tax_enabled','fiscal_year_start','scrap_warehouse_id'];
    const d = {}; keys.forEach(k=>d[k] = fieldVal(k));
    const r = await apiTry('settings', {method:'POST', body:d});
    if(r!==null){ toast('تنظیمات ذخیره شد','ok'); this.meta.settings = await api('settings');
      $('#topCompany').textContent = d.company_name || 'فروشگاه باتری'; }
  },
  changePass(){ modalForm('تغییر گذرواژه', [
      {name:'p_old', label:'گذرواژه فعلی', type:'password'},
      {name:'p_new', label:'گذرواژه جدید', type:'password'}], null,
    `<button class="btn primary" onclick="App.doChangePass()">ذخیره</button><button class="btn" onclick="App.closeModal()">انصراف</button>`); },
  async doChangePass(){ const r = await apiTry('account/password', {method:'POST', body:{old:fieldVal('p_old'), new:fieldVal('p_new')}});
    if(r!==null){ this.closeModal(); toast('گذرواژه تغییر کرد','ok'); } },

});

/* ============================== راه‌اندازی ============================== */
window.App = App;
window.JDate = JDate;
window.addEventListener('DOMContentLoaded', () => App.boot());
