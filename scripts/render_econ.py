#!/usr/bin/env python3
"""生成「天辉经济/经验优势时间线」图。SVG python 端直接算点串, chrome 截图成 PNG。
用法: python3 render_econ.py <mid> [out.png]"""
import json,os,sys,re,subprocess,tempfile
REV="/home/iceamber/.openclaw/workspace/dota2-platform/site/data/reviews"

def load(mid):
    p=f"/tmp/m/{mid}.json"
    if not os.path.exists(p):
        import urllib.request
        req=urllib.request.Request(f"https://api.opendota.com/api/matches/{mid}",headers={'User-Agent':'dota/1.0'})
        with urllib.request.urlopen(req,timeout=180) as r: open(p,'wb').write(r.read())
    return json.load(open(p))

def build(mid,outp):
    d=load(mid)
    gold=[float(x) for x in (d.get('radiant_gold_adv') or [])]
    xp  =[float(x) for x in (d.get('radiant_xp_adv') or [])]
    dur=float(d.get('duration',0)); n=len(gold) or 1; step=dur/n/60.0
    tmax=max(n*step,1)
    ti=json.load(open(f"{REV}/ti_index.json"))
    tag=(ti.get(mid) or {})
    rt=tag.get('radiant_tag') or '天辉'; dt=tag.get('dire_tag') or '夜魇'
    W,H=1320,600; m=64; bw=W-2*m; base=H/2; pad=46
    # 事件
    ev=[]
    for o in (d.get('objectives') or []):
        ty=o.get('type'); t=o.get('time')/60.0
        if ty=='building_kill':
            k=o.get('key') or ''; side='rad' if 'goodguys' in k else 'dire'
            lv=re.search(r'tower(\d)',k); lv=int(lv.group(1)) if lv else 0
            ev.append((t,side,'t',lv))
        elif ty=='CHAT_MESSAGE_ROSHAN_KILL':
            tm=o.get('team'); side='dire' if tm==3 else ('rad' if tm==2 else '?')
            ev.append((t,side,'r',0))
    def mx(t): return m+(t/tmax)*bw
    amax=max([abs(v) for v in gold]+[abs(v) for v in xp]+[1])
    scale=amax*1.06
    def my(v): return base-(v/scale)*(H/2-pad)
    def mk(polycol,vals,op,dash=None,wide=2.6):
        pts=" ".join(f"{mx(i*step):.1f},{my(v):.1f}" for i,v in enumerate(vals) if i< n)
        extra=f' stroke-dasharray="{dash}"' if dash else ''
        return f'<polyline points="{pts}" fill="none" stroke="{polycol}" stroke-opacity="{op}" stroke-width="{wide}"{extra}/>'
    s=[]
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="WenQuanYi Micro Hei,Noto Sans CJK SC,sans-serif">')
    s.append(f'<rect width="{W}" height="{H}" fill="#0c111c"/>')
    # 网格/轴: 每5分钟 x
    s.append(f'<rect x="{m}" y="{pad*0.5:.0f}" width="{bw}" height="{H-pad}" fill="none" stroke="#23304a"/>')
    for mm in range(0,int(tmax)+1,5):
        xx=mx(mm)
        s.append(f'<line x1="{xx:.0f}" y1="{pad*0.5}" x2="{xx:.0f}" y2="{H-pad*0.5}" stroke="#1b2436" stroke-width="1.4"/>')
        s.append(f'<text x="{xx:.0f}" y="{H-8}" fill="#7d8aa3" font-size="13" text-anchor="middle">{mm}′</text>')
    # y grid 0 + 四分位
    s.append(f'<line x1="{m}" y1="{base:.0f}" x2="{W-m}" y2="{base:.0f}" stroke="#3a4a6b" stroke-width="1.8"/>')
    for lab,fr in (('+'+('{:.0f}k'.format(scale*0.5/1000)),0.5),('0',0),('-'+('{:.0f}k'.format(scale*0.5/1000)),-0.5)):
        yy=my(scale*fr*0) # no
    # gold 正绿负红: 分别两段线
    # 拆成若干段按符号
    def segs(vals):
        out=[];cur=[];sign=None
        for i,v in enumerate(vals):
            sg=1 if v>=0 else -1
            if sign is None or sg==sign: cur.append((i,v))
            else:
                out.append((sign,cur)); cur=[(i-1,vals[i-1]),(i,v)]
            sign=sg
        if cur: out.append((sign,cur))
        return out
    G='#4cc96a';R='#ec6f7a'
    for sign,cur in segs(gold):
        col= G if sign>0 else R
        pts=" ".join(f"{mx(i*step):.1f},{my(v):.1f}" for i,v in cur)
        s.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="3" stroke-linejoin="round"/>')
    # xp 虚线(蓝色, 缩放同 scale)
    s.append(mk('#7fd3ff',xp,0.9,dash='5 5',wide=1.8))
    # 图例标题
    s.append(f'<text x="{m}" y="26" fill="#eef3fb" font-size="20" font-weight="bold">经济支配曲线 · 天辉 vs 夜魇</text>')
    s.append(f'<text x="{W-m}" y="26" fill="#9fb0cc" font-size="15" text-anchor="end">{rt}（天辉） vs {dt}（夜魇）</text>')
    s.append(f'<g font-size="13">'
             f'<circle cx="{W-m-330}" cy="{H-16}" r="4" fill="#4cc96a"/><text x="{W-m-322}" y="{H-12}" fill="#cfd9ea">天辉领先</text>'
             f'<circle cx="{W-m-180}" cy="{H-16}" r="4" fill="#ec6f7a"/><text x="{W-m-172}" y="{H-12}" fill="#cfd9ea">夜魇领先</text>'
             f'<circle cx="{W-m-60}" cy="{H-16}" r="4" fill="none" stroke="#7fd3ff"/><text x="{W-m-52}" y="{H-12}" fill="#cfd9ea">经验差</text>'
             f'</g>')
    s.append('</svg>')
    html=f"""<!doctype html><html><head><meta charset=utf-8><style>body{{margin:0;background:#0c111c;width:{W}px}}img{{display:block}}</style></head><body>{''.join(s)}</body></html>"""
    f=tempfile.mktemp('.html');open(f,'w').write(html)
    o=tempfile.mktemp('.png')
    ch=os.environ.get('CHROME','google-chrome')
    r=subprocess.run([ch,'--headless=new','--disable-gpu','--no-sandbox','--hide-scrollbars',f'--window-size={W},{H}',f'--screenshot={o}',f'file:///{f}'],capture_output=True,text=True)
    os.remove(f)
    if os.path.exists(o):
        os.makedirs(os.path.dirname(outp),exist_ok=True); os.replace(o,outp)
        print("OK",outp)
    else:
        print("FAIL", r.stderr[-500:])

if __name__=='__main__':
    mid=sys.argv[1]; build(mid, sys.argv[2] if len(sys.argv)>2 else f"{REV}/{mid}-econ.png")
