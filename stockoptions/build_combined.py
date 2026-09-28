#!/usr/bin/env python3
"""Merge the HSI and stock option dashboards into ONE page with top tabs.

No iframes: both dashboards' DOM live in the same document, each inline
<script> wrapped in an IIFE. Stock element ids are prefixed with 's_' and the
stock IIFE shadows `document` with a Proxy that prefixes id lookups, so both
dashboards' JS run unmodified without collisions.
"""
import datetime
import os
import re

DIR = os.path.expanduser('~/workspace/your_files/hsioptions')
HSI = os.path.join(DIR, '恆指期權倉數儀表板.html')
STK = os.path.join(DIR, '股票期權倉數儀表板.html')
OUT = os.path.join(DIR, '期權倉數儀表板.html')
OUT_EN = os.path.join(DIR, 'options-dashboard.html')
REF_FRAG = os.path.expanduser('~/workspace/stockoptions/quant/strategy_ref_body.html')
PTS_FRAG = os.path.expanduser('~/workspace/stockoptions/quant/nightly_points_body.html')

CDN = ''  # Chart.js is now inlined inside each dashboard (offline-safe); no CDN needed

GUARD = 'if(window!==window.top)document.querySelectorAll(\'.boardtabs\').forEach(e=>e.remove());'


def _html_ent(ch):
    o = ord(ch)
    return ch if o < 0x80 else f'&#x{o:X};'


def _js_esc(ch):
    o = ord(ch)
    if o < 0x80:
        return ch
    if o <= 0xFFFF:
        return f'\\u{o:04x}'
    o -= 0x10000
    return f'\\u{0xD800 + (o >> 10):04x}\\u{0xDC00 + (o & 0x3FF):04x}'


def _css_esc(ch):
    o = ord(ch)
    return ch if o < 0x80 else f'\\{o:X} '


_NONASCII = re.compile(r'[^\x00-\x7F]')
_TOKEN = re.compile(r'<!--.*?-->|<script>.*?</script>|<style>.*?</style>', re.S)


def ascii_safe(html):
    """Make the page pure ASCII so it renders correctly even if the viewer
    decodes the file as Latin-1 instead of UTF-8 (meta charset ignored).

    - HTML text/attributes/comments -> numeric character references
    - inline <script> -> \\uXXXX escapes (runtime strings unchanged)
    - inline <style>  -> CSS escapes
    """
    out = []
    pos = 0
    for m in _TOKEN.finditer(html):
        out.append(_NONASCII.sub(lambda x: _html_ent(x.group(0)), html[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith('<script>'):
            inner = tok[len('<script>'):-len('</script>')]
            out.append('<script>' + _NONASCII.sub(lambda x: _js_esc(x.group(0)), inner) + '</script>')
        elif tok.startswith('<style>'):
            inner = tok[len('<style>'):-len('</style>')]
            out.append('<style>' + _NONASCII.sub(lambda x: _css_esc(x.group(0)), inner) + '</style>')
        else:
            out.append('<!--' + _NONASCII.sub(lambda x: _html_ent(x.group(0)), tok[4:-3]) + '-->')
        pos = m.end()
    out.append(_NONASCII.sub(lambda x: _html_ent(x.group(0)), html[pos:]))
    return ''.join(out)


def split_page(path):
    s = open(path, encoding='utf-8').read()
    styles = re.findall(r'<style>(.*?)</style>', s, re.S)
    # inline scripts: vendored libraries first (in <head>), dashboard script last (end of <body>)
    scripts = re.findall(r'<script>(.*?)</script>', s, re.S)
    assert len(scripts) >= 1, f'{path}: no inline script found'
    libs, main_js = scripts[:-1], scripts[-1]
    assert 'init();' in main_js or 'render()' in main_js, f'{path}: last script does not look like the dashboard script'
    body = re.search(r'<body>(.*?)</body>', s, re.S).group(1)
    return styles, libs, main_js, body


def strip_sitefoot_div(body):
    # remove <div class="sitefoot">...</div> with correct nesting (inner divs exist)
    start = body.find('<div class="sitefoot">')
    if start < 0:
        return body
    depth = 0
    for m in re.finditer(r'</?div\b[^>]*>', body[start:]):
        depth += -1 if m.group(0).startswith('</') else 1
        if depth == 0:
            return body[:start] + body[start + m.end():]
    return body


def clean_body(body):
    # drop the per-dashboard tab nav (wrapper has its own tabs)
    body = re.sub(r'<nav class="boardtabs">.*?</nav>', '', body, flags=re.S)
    # drop per-section footers (merged page has one global footer at the bottom)
    body = re.sub(r'<footer[^>]*>.*?</footer>', '', body, flags=re.S)
    body = strip_sitefoot_div(body)
    # drop the inline <script> (it sits inside <body>; we re-add it once, wrapped in an IIFE)
    body = re.sub(r'<script>.*?</script>', '', body, flags=re.S)
    return body


def prefix_ids(body, prefix='s_'):
    body = re.sub(r'id="([A-Za-z][\w-]*)"',
                  lambda m: f'id="{prefix}{m.group(1)}"', body)
    body = re.sub(r'for="([A-Za-z][\w-]*)"',
                  lambda m: f'for="{prefix}{m.group(1)}"', body)
    return body


STOCK_PRE = r"""(function(){
/* namespace shim: stock dashboard ids are prefixed with s_ in this merged page */
const document = new Proxy(window.document, {
  get(t, p, r){
    if(p === 'getElementById') return (id) => t.getElementById('s_' + id);
    if(p === 'querySelector') return (sel) => t.querySelector(sel.replace(/#([A-Za-z][\w-]*)/g, '#s_$1'));
    if(p === 'querySelectorAll') return (sel) => t.querySelectorAll(sel.replace(/#([A-Za-z][\w-]*)/g, '#s_$1'));
    const v = Reflect.get(t, p, r);
    return (typeof v === 'function') ? v.bind(t) : v;
  }
});
"""

WRAPPER_CSS = """
.topbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;margin-bottom:14px}
.topbar h1{font-size:1.5rem;letter-spacing:1px}
.topbar h1 .dot{color:var(--gold)}
.topbar .sub{color:var(--dim);font-size:.8rem}
.boardtabs{display:flex;gap:4px;background:var(--card);border:1px solid var(--line);border-radius:24px;padding:4px}
.boardtabs button{background:none;border:0;color:var(--dim);padding:8px 22px;border-radius:18px;font-size:.95rem;cursor:pointer;white-space:nowrap;font-family:inherit}
.boardtabs button.on{background:var(--gold);color:#111;font-weight:700}
.boardtabs button:not(.on):hover{color:var(--txt)}
"""

TAB_JS = """
document.querySelectorAll('.boardtabs button').forEach(b=>b.onclick=()=>{
  const t=b.dataset.t;
  document.querySelectorAll('.boardtabs button').forEach(x=>x.classList.toggle('on',x===b));
  document.getElementById('pane-hsi').hidden = (t!=='hsi');
  document.getElementById('pane-stk').hidden = (t!=='stk');
  document.getElementById('pane-ref').hidden = (t!=='ref');
  document.getElementById('pane-pts').hidden = (t!=='pts');
  try{history.replaceState(null,'','#'+t);}catch(e){}
  setTimeout(()=>{try{window.dispatchEvent(new Event('resize'));}catch(e){}},60);
  setTimeout(()=>{try{window.dispatchEvent(new Event('resize'));}catch(e){}},600);
});
(function(){const t=location.hash.replace('#','');if(t==='stk'||t==='ref')document.querySelector('.boardtabs button[data-t="'+t+'"]').click();})();
"""


def split_ref(path):
    s = open(path, encoding='utf-8').read()
    styles = re.findall(r'<style>(.*?)</style>', s, re.S)
    body = re.sub(r'<style>.*?</style>', '', s, flags=re.S)
    return styles, body


GLOBAL_FOOT = """<footer class="sitefoot">
<div class="cp">© {year} <b>期權倉影</b> 版權所有</div>
<div><span class="dtitle">免責聲明：</span>本頁所有資料、數據及圖表僅供參考，不構成投資建議。本網頁內容並非投資意見，亦不構成任何投資產品之要約、要約招攬或建議。本資料僅作一般資訊用途，並未考慮您的個人需要、投資目標及特定財政狀況。期權涉及槓桿及高風險，價格可升可跌，買賣期權可能損失全部投入資金。過往表現並非未來表現之指標。在作出任何投資決定前，請先自行評估風險，並諮詢持牌專業顧問之獨立意見。</div>
<div class="src">數據來源：恆指期權未平倉數據（hkiei.com/hsioptiondata）；股票期權（港交所每日市場報告 DMR）。股票期權月份標籤如 SEP-26·25日 代表同月到期之週期權，冇後綴者為月期權；大戶框架只適用於月期權。</div>
</footer>"""


def main():
    hsi_styles, hsi_libs, hsi_js, hsi_body = split_page(HSI)
    stk_styles, stk_libs, stk_js, stk_body = split_page(STK)
    ref_styles, ref_body = split_ref(REF_FRAG)
    pts_styles, pts_body = split_ref(PTS_FRAG)
    # dedupe vendored libraries (both dashboards inline the same Chart.js)
    seen, libs = set(), []
    for lib in hsi_libs + stk_libs:
        if lib not in seen:
            seen.add(lib); libs.append(lib)
    libs_html = ''.join(f'<script>{lib}</script>\n' for lib in libs)

    hsi_body = clean_body(hsi_body)
    stk_body = prefix_ids(clean_body(stk_body), 's_')
    ref_body = prefix_ids(ref_body, 'r_')
    pts_body = prefix_ids(pts_body, 'r_')
    hsi_js = hsi_js.replace(GUARD, '')
    stk_js = stk_js.replace(GUARD, '')

    # sanity: no duplicate ids across the merged document
    ids = re.findall(r'id="([A-Za-z][\w-]*)"', hsi_body + stk_body + ref_body + pts_body)
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f'duplicate ids: {dupes}'

    style_html = ('<style>' + WRAPPER_CSS + '</style>\n'
                  + ''.join(f'<style>{s}</style>\n' for s in hsi_styles + stk_styles + ref_styles + pts_styles))
    foot = GLOBAL_FOOT.format(year=datetime.date.today().year)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>期權倉影 - 大戶佈局拆解</title>
{style_html}{libs_html}
</head>
<body>
<header class="topbar">
<div><h1>期權倉影 <span class="dot">·</span> 大戶佈局拆解</h1>
<div class="sub">恆指期權 + 股票期權 · 每日盤後更新</div></div>
<nav class="boardtabs"><button class="on" data-t="hsi">恆指期權</button><button data-t="stk">股票期權</button><button data-t="ref">今日策略參考</button><button data-t="pts">每日重點手影</button></nav>
</header>
<section id="pane-hsi">
{hsi_body}
</section>
<section id="pane-stk" hidden>
{stk_body}
</section>
<section id="pane-ref" hidden>
{ref_body}
</section>
<section id="pane-pts" hidden>
{pts_body}
</section>
{foot}
<script>
(function(){{
{hsi_js}
}})();
</script>
<script>
{STOCK_PRE}
{stk_js}
}})();
</script>
<script>
{TAB_JS}
</script>
</body>
</html>"""

    for p in (OUT, OUT_EN):
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(ascii_safe(html))
    # sanity: output must be pure ASCII
    raw = open(OUT, 'rb').read()
    assert all(b < 128 for b in raw), 'non-ASCII bytes left in output'
    print('saved', OUT, f'{len(raw)//1024}KB', '(ascii-safe)')


if __name__ == '__main__':
    main()
