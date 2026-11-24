"""Render the saved inference results as a self-contained, offline walkthrough."""
from html import escape
from pathlib import Path
from decimal import Decimal
import json

from run import ROOT, classify_charges, ledger, read_json, validate


def esc(value):
    return escape(str(value), quote=True)


def money(value, currency):
    return "待确认" if value is None else f"{currency} {Decimal(str(value)):,.2f}"


def code(value):
    return "<pre><code>" + esc(value) + "</code></pre>"


def lines_view(case):
    rows = "".join(f"<li><span>{esc(line)}</span></li>" for line in case["lines"])
    return f'<ol class="lines">{rows}</ol>'


def source_link(case):
    if not case["source"]:
        return ""
    return f'<a href="{esc(case["source"])}" rel="noreferrer">查看主办方原文 ↗</a>'


def assumptions(c):
    ccy = c["currency"]
    return f'摊主自填　售价 {money(c["price"], ccy)}／件，单件成本 {money(c["unit_cost"], ccy)}，收款费率 {Decimal(c["payment_rate"])*100:g}%，自付固定开支 {money(c["own_fixed"], ccy)}。'


def totals_view(c, row):
    if "review" in row:
        return '<p class="notice">引文校验未通过，请核对公告。'+esc(row["review"])+'</p>'
    t, cur = row["totals"], c["currency"]
    units = "待确认" if t["units"] is None else str(t["units"])+" 件"
    items = [("本场已列开支", money(t["expense"],cur)), ("公告列出的可退押金", money(t["deposits"],cur)),
             ("含押金需备资金", money(t["cash"],cur)), ("覆盖已列开支的销量", units)]
    cards = "".join(f'<div><dt>{esc(name)}</dt><dd>{esc(val)}</dd></div>' for name,val in items)
    if t["expense"] is None:
        detail = f'摊租仍需确认。目前可以加总的开支和押金为 {money(t["known_cash"],cur)}。'
    else:
        detail = f'每件商品可抵开支 {money(t["margin"],cur)}。按整件向上取整，可退押金仅计入需备资金。'
    return '<dl class="metrics">'+cards+'</dl><p>'+esc(detail)+'</p><p class="muted">'+esc(assumptions(c))+'</p>'


def sections(cases, rows, evidence):
    lead = cases[0]
    card = read_json(evidence/"source-card.json")
    parsed = json.loads(card["content"])
    excerpts = parsed.get("documents", [{}])[0].get("evidence", {})
    quotes = [q for q in excerpts.values() if isinstance(q,str) and any(q and q in s for s in lead["lines"])]
    skill_list = "".join(f"<li>{esc(q)}</li>" for q in dict.fromkeys(quotes))
    first = f'''<h2>两天市集，要交几次清洁费？</h2>
    <p class="intro">高雄的一份招摊简章把整场清洁费和天数写在同一行。摊主需要把这笔钱填进出摊预算。</p>
    <h3>输入给模型的节选</h3>{lines_view(lead)}
    <div class="credit">{esc(lead["location"])} {source_link(lead)}</div>
    <h3>SkillHub 信息卡中的可核对摘录</h3><ul>{skill_list}</ul>
    <p class="muted">技能版本 20260807.064126。程序逐条核对引文，只把能在输入中找到的文字交给下一步。</p>'''
    raw = read_json(evidence/"kaohsiung.json")["content"]
    first_try = read_json(ROOT/"first-pass"/"kaohsiung.json")["content"]
    middle = read_json(ROOT/"quote-pass"/"kaohsiung.json")["content"]
    second = '<h2>同一句「500元/2天」，哪里会算错？</h2><h3>第一次 · 让模型写金额和单位</h3>'+code(first_try)
    second += '<p>模型漏掉了免租，并写成按天收费。直接乘两天会把清洁费翻倍。</p>'
    second += '<h3>第二次 · 让模型自行摘录收费条款</h3>'+code(middle)
    second += '<p>这次留下了免租，却漏掉了清洁费。</p><h3>第三次 · 先拆出两条，再由模型逐条分类</h3>'
    second += '<p><code>每攤位免租金</code>　／　<code>但須繳交清潔費500元/2天</code></p>'+code(raw)
    second += '<p class="muted">以上为三个版本实际返回的文本。程序从所选原文读取金额，并按公告覆盖的天数计算。</p>'
    third = '<h2>把收费条款换成出摊预算</h2><h3>高雄 · 一个摊位 · 两天</h3>'+totals_view(lead,rows[0])
    third += '<h3>同一份虚构公告，只改用电选择</h3><p>纸上小集的场租含两天，展具押金可退。租用电源每天加 20 元。</p>'
    third += '<div class="table-wrap"><table><thead><tr><th>摊主选择</th><th>本场开支</th><th>押金</th><th>含押金需备</th><th>保本量</th></tr></thead><tbody>'
    for c,r in zip(cases[3:5],rows[3:5]):
        t = r.get("totals", {})
        cells = [c["name"],money(t.get("expense"),"CNY"),money(t.get("deposits"),"CNY"),money(t.get("cash"),"CNY"),
                 "待确认" if t.get("units") is None else str(t["units"])+" 件"]
        third += '<tr>'+''.join('<td>'+esc(x)+'</td>' for x in cells)+'</tr>'
    third += '</tbody></table></div><p class="muted">自填经营数据均为演示假设。预算不含备货占款、未列费用和本人工资。</p>'
    passed = sum(r.get("score",{}).get("all_exact",False) for r in rows)
    original_pass = sum(r.get("score",{}).get("all_exact",False) for r in rows[:6])
    extra_pass = sum(r.get("score",{}).get("all_exact",False) for r in rows[6:])
    fourth = f'<h2>八种出摊情境，逐例看结果</h2><p class="intro">调整后，原六例有 {original_pass} 例、新增两例有 {extra_pass} 例在费用分类、单价、计价单位、行号和四项预算上全部符合预先记录的答案。共 {passed}/{len(rows)} 例。点击场景可展开原文和运行记录。</p>'
    for c,r in zip(cases,rows):
        raw = read_json(evidence/(c["id"]+".json"))["content"]
        ok = r.get("score",{}).get("all_exact",False)
        fourth += f'<details><summary>{esc(c["name"])} <small>{esc(c["kind"])}　{"全项相符" if ok else "需复核"}</small></summary><p>{esc(c["scenario"])}</p>{lines_view(c)}<p class="credit">{esc(c["location"])} {source_link(c)}</p>{code(raw)}{totals_view(c,r)}</details>'
    fourth += '<p class="muted">四个场景来自公开资料，四个为原创情境，其中两个共用一份公告。除公告摘录外，售价、成本和出摊选择均为假设。结果仅覆盖这组小样本。</p>'
    fresh_cases = read_json(ROOT/"fresh-cases.json")
    fridge, metres = fresh_cases
    fresh_results = read_json(ROOT/"fresh"/"results.json")["cases"]
    fridge_raw = read_json(ROOT/"fresh"/"cyanotype.json")["content"]
    fifth = '<h2>换两份新公告，哪里还需要人？</h2><p class="intro">定稿后才试的两个场景中，一例正确停算，一例漏费。前面八例参与过调整。</p>'
    fifth += '<h3>一摊两天，两天都租小冰箱</h3>'+lines_view(fridge)+code(fridge_raw)
    fifth += '<p>模型把已选冰箱标成 <code>skip</code>。这会少计 24 元，把保本量从 10 件低估为 9 件。摊主可以按自己的实际选择复核。</p>'
    selected = json.loads(fridge_raw)["labels"]
    options = ['<option value="">请选择</option>']
    for label, text in [("service","两天都租冰箱"),("skip","不用冰箱")]:
        labels = selected[:-1]+[label]
        fees = validate(fridge,{"charges":classify_charges(fridge,{"labels":labels})})
        recalculated = ledger(fridge,fees)
        display = f'本场开支 {money(recalculated["expense"],"CNY")}　含押金需备 {money(recalculated["cash"],"CNY")}　保本 {recalculated["units"]} 件'
        options.append(f'<option value="{esc(display)}">{text}</option>')
    fifth += '<label for="fridge">实际租用情况　</label><select id="fridge">'+"".join(options)+'</select><p class="choice" id="confirmed" aria-live="polite">确认后显示核算结果。</p>'
    fifth += '<h3>英国瑟斯克 · 摊位按宽度收费</h3>'
    fifth += '<p>5 米摊位，每米 6.85 英镑，最低 27.40 英镑。程序在超出计价范围时留下「'+esc(fresh_results[1]["review"])+'」。按公告手算为 34.25 英镑。 '+source_link(metres)+'</p>'
    return [first,second,third,fourth,fifth]


CSS = """
:root{color-scheme:light;font:16px/1.55 "DM Sans","Noto Sans CJK SC","Microsoft YaHei",sans-serif;color:#202c27;background:#f5f4ee}
*{box-sizing:border-box}body{margin:0}main{max-width:1050px;margin:26px auto;padding:0 24px 38px}
header{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:0 0 20px;padding:14px 2px;border-bottom:1px solid #b4c8bc}
h1{font-size:23px;margin:0;letter-spacing:.04em}header span{font-size:14px;color:#50665a}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 16px}nav a{padding:7px 19px;border-radius:5px;text-decoration:none;color:#264f40}
nav a[aria-current=page]{background:#1b5949;color:white}nav a:focus-visible,summary:focus-visible{outline:3px solid #d99b38}
section{background:#fffdf8;border:1px solid #c9d4cb;border-top:4px solid #437761;border-radius:8px;padding:24px 34px 22px}
h2{font-size:clamp(23px,3vw,32px);margin:0 0 8px;line-height:1.35;letter-spacing:-.035em}
h3{font-size:17px;margin:19px 0 8px;color:#244b3d}p{margin:8px 0 12px}.intro{color:#3d5045;max-width:780px}
.lines{counter-reset:line;list-style:none;margin:7px 0;padding:5px 15px;background:#eff3ea;border-radius:6px}
.lines li{counter-increment:line;display:flex;align-items:baseline;gap:14px;padding:7px 0}.lines li:before{content:counter(line);font:13px monospace;color:#577260}
.credit,.muted,small{font-size:13px;color:#52635a}.credit a,a{color:#176449}ul{margin:5px 0 12px;padding-left:24px}
pre{margin:12px 0;background:#edf1ec;border:1px solid #cbd7cd;border-radius:6px;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45;font-size:14px}code{font-family:"IBM Plex Mono","Noto Sans Mono CJK SC",monospace}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:13px 0}.metrics div{background:#eef4e9;border:1px solid #cedbcb;border-radius:5px;padding:12px}
dt{font-size:13px;color:#476151}dd{margin:4px 0 0;font-size:clamp(18px,2.5vw,26px);font-weight:650;color:#164d3c}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:14px}th,td{padding:9px 10px;border-bottom:1px solid #d8dfd6}th{background:#ebf0e7;color:#345943}
details{border-top:1px solid #d6dfd5;padding:10px 1px}summary{cursor:pointer;font-weight:600}summary small{float:right;font-weight:400}.notice{color:#864c1d}
select{font:inherit;color:#244b3d;border:1px solid #a9bdb0;border-radius:5px;padding:4px 12px;background:#fff}.choice{padding:9px 12px;background:#eaf3e6;border-radius:5px;color:#244b3d;font-weight:600}
@media(max-width:680px){main{margin:12px auto;padding:0 12px}section{padding:17px}header{display:block}nav a{padding:6px 10px}.metrics{grid-template-columns:1fr 1fr}summary small{float:none;display:block}}
@media print{nav{display:none}section[hidden]{display:block}section{break-before:page}}
"""


def render(evidence, destination):
    cases = read_json(ROOT/"cases.json")
    pages = sections(cases,read_json(evidence/"results.json"),evidence)
    tabs = [("source","公告和技能"),("model","模型原文"),("budget","出摊预算"),("check","逐例复核"),("fresh","新公告与人工复核")]
    nav = "".join(f'<a href="#{key}">{label}</a>' for key,label in tabs)
    content = "".join(f'<section id="{key}">{page}</section>' for (key,_),page in zip(tabs,pages))
    js = """function selectPage(){const pages=[...document.querySelectorAll('section')];const target=pages.find(p=>'#'+p.id===location.hash)||pages[0];pages.forEach(p=>p.hidden=p!==target);document.querySelectorAll('nav a').forEach(a=>{if(a.hash==='#'+target.id)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});window.scrollTo(0,0)}window.addEventListener('hashchange',selectPage);selectPage();"""
    js += """document.getElementById('fridge').addEventListener('change',e=>document.getElementById('confirmed').textContent=e.target.value||'确认后显示核算结果。');"""
    destination.write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>市集摊费核算手记</title><style>{CSS}</style><main><header><h1>市集摊费核算手记</h1><span>Spark-X2.6-4B · 本地运行记录</span></header><nav aria-label="查看运行记录">{nav}</nav>{content}</main><script>{js}</script></html>',encoding="utf-8")


if __name__ == "__main__":
    render(ROOT/"evidence", ROOT/"report.html")
