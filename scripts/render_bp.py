#!/usr/bin/env python3
# 生成任意场次官方观战风格 BP 面板 PNG（复用 G5 已验证版面）: python3 bp_any.py <mid> [hero名用中文,需 herostats]
import json,os,sys,base64,urllib.request,re,subprocess,tempfile
REV="/home/iceamber/.openclaw/workspace/dota2-platform/site/data/reviews"
HSRC="/home/iceamber/.openclaw/workspace/dota2-platform/site/data/herostats.json"

def load(mid):
    p=f"/tmp/m/{mid}.json"
    if not os.path.exists(p):
        import urllib.request
        req=urllib.request.Request(f"https://api.opendota.com/api/matches/{mid}",headers={'User-Agent':'dota-comm/1.0'})
        with urllib.request.urlopen(req,timeout=180) as r: open(p,'wb').write(r.read())
    return json.load(open(p))

def hero_cn_map():
    hs=json.load(open(HSRC)); return {h['id']:h for h in hs['heroes']}
def b64(path):
    return 'data:image/png;base64,'+base64.b64encode(open(path,'rb').read()).decode() if os.path.exists(path) else ''

def build(mid,outp,title=None,sub=None):
    d=load(mid); pb=sorted(d.get('picks_bans') or [],key=lambda z:z.get('order',0))
    HM=hero_cn_map()
    cache="/tmp/bpimg";os.makedirs(cache,exist_ok=True)
    dic={} # hero_id->cn
    for x in pb:
        h=x['hero_id']; 
        if h not in dic: dic[h]=(HM.get(h) or {}).get('name') or str(h)
        p=f"{cache}/{h}.png"
        if (HM.get(h) or {}).get('img') and not (os.path.exists(p) and os.path.getsize(p)>500):
            try:
                req=urllib.request.Request((HM.get(h)).get('img'),headers={'User-Agent':'Mozilla'})
                with urllib.request.urlopen(req,timeout=25) as r: raw=r.read()
                if len(raw)>500: open(p,'wb').write(raw)
            except Exception: pass
    picks0=[x for x in pb if x.get('is_pick') and x.get('team')==0]
    picks1=[x for x in pb if x.get('is_pick') and x.get('team')==1]
    bans0 =[x for x in pb if not x.get('is_pick') and x.get('team')==0]
    bans1 =[x for x in pb if not x.get('is_pick') and x.get('team')==1]
    ti=json.load(open(f"{REV}/ti_index.json")); tag=(ti.get(mid) or {})
    RT=tag.get('radiant_tag') or '天辉'; DT=tag.get('dire_tag') or '夜魇'
    radwin=d.get('radiant_win')
    def cn(x): return dic[x['hero_id']]
    # html (like G5 layout)
    def hc(ids,small=False,ban=False):
        w='46px' if ban else '116px'
        out=[]
        for x in ids:
            p=f"{cache}/{x['hero_id']}.png"; img=b64(p)
            filt=' filter:grayscale(1) brightness(.66)' if ban else ''
            out.append(f'<div class="h" style="width:{w}"><img src="{img}" style="width:{w};height:{w}{filt}"><span>{cn(x)}</span></div>')
        return ''.join(out)
    grn='#4cc96a'; red='#ec6f7a'
    bansec0=hc(bans0,ban=True); bansec1=hc(bans1,ban=True)
    pick0=hc(picks0); pick1=hc(picks1)
    if title is None:
        title='THE INTERNATIONAL 2026 · 总决赛'
    h=f"""<!doctype html><meta charset=utf-8><style>
*{{box-sizing:border-box;margin:0}}body{{background:#0c111c;width:1380px;font-family:'WenQuanYi Micro Hei','Noto Sans CJK SC',sans-serif;color:#e6ecf5}}
.banner{{display:flex;align-items:baseline;gap:18px;padding:18px 30px 12px;border-bottom:2px solid #223048}}
.banner .t{{font-size:30px;font-weight:700}} .banner .s{{color:#8fa0bc;font-size:16px}}
.split{{display:flex}}
.col{{flex:1;padding:14px 20px}}
.colL{{}} .colR{{text-align:right}}
.head{{font-size:24px;font-weight:700;display:flex;align-items:baseline;gap:10px;justify-content:space-between}}
.picks{{display:flex;gap:10px;margin-top:8px;flex-wrap:wrap}}
.colR .picks,.colR .bans{{flex-direction:row-reverse;justify-content:flex-start}}
.h:is(.colR *) .h{{margin-left:0}}
.bansec{{margin-top:14px;border-top:1px solid #223048;padding-top:8px}}
.lbl{{font-size:15px;color:#56617a;letter-spacing:3px;margin-bottom:6px}}
.bans{{display:flex;gap:7px;flex-wrap:wrap}}
.h span{{display:block;font-size:13px;color:#d4deec;margin-top:3px;white-space:nowrap;overflow:hidden}}
.h img{{object-fit:cover;border-radius:8px;display:block}}
.bans img{{border-radius:6px}}
.colR .head{{flex-direction:row-reverse}}
.vs{{width:90px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#7c88a0;gap:6px;font-size:18px}}
.g{{color:#4cc96a}} .d{{color:#ec6f7a}}
</style><body><div class="banner"><span class="t">{title}</span><span class="s">{sub or ''}</span></div>
<div class="split">
 <div class="col colL"><div class="head"><span class="g">{RT}</span><span style="color:#8fa0bc;font-size:15px">天辉 RADIANT</span></div>
  <div class="picks">{pick0}</div>
  <div class="bansec"><div class="lbl">BAN</div><div class="bans">{bansec0}</div></div></div>
 <div class="vs"><div>VS</div><div>🏆 {('天辉' if radwin else '夜魇')}胜</div></div>
 <div class="col colR"><div class="head" style="justify-content:flex-start"><span class="d">{DT}</span><span style="color:#8fa0bc;font-size:15px">夜魇 DIRE</span></div>
  <div class="picks">{pick1}</div>
  <div class="bansec"><div class="lbl" style="text-align:right">BAN</div><div class="bans" style="justify-content:flex-end">{bansec1}</div></div></div>
</div></body>"""
    f=tempfile.mktemp('.html');open(f,'w').write(h)
    o=tempfile.mktemp('.png')
    ch=os.environ.get('CHROME','google-chrome')
    r=subprocess.run([ch,'--headless=new','--disable-gpu','--no-sandbox','--hide-scrollbars','--force-device-scale-factor=1','--window-size=1380,640',f'--screenshot={o}',f'file:///{f}'],capture_output=True,text=True)
    os.remove(f)
    if os.path.exists(o): os.makedirs(os.path.dirname(outp),exist_ok=True); os.replace(o,outp); print("OK",outp)
    else: print("FAIL",r.stderr[-400:])

if __name__=='__main__':
    mid=sys.argv[1]
    build(mid, sys.argv[2] if len(sys.argv)>2 else f"{REV}/{mid}-bp.png")
