"""Generate the hosted read-only viewer from the shared dashboard template."""
from pathlib import Path
import argparse


def build(out):
    source = (Path(__file__).resolve().parents[1] / 'src/ai_radar/dashboard.html').read_text()
    source = source.replace('const DATA=/*__RADAR_DATA__*/null;', '''async function startRadar(){
const response=await fetch('https://api.github.com/repos/Chenxiao-Tian/Data_Collection/contents/companies.json?ref=ai-radar-data', {cache:'no-store',headers:{Accept:'application/vnd.github.raw+json'},signal:AbortSignal.timeout(20000)});
if(!response.ok) throw new Error('暂时未能取得采集快照（HTTP '+response.status+'）');
const DATA=await response.json();
if(!Array.isArray(DATA.companies))throw new Error('数据格式不正确');''')
    source = source.replace("draw();if(location.protocol!=='file:')fetch('/health').then(r=>r.ok?r.json():null).then(v=>{if(v?.status==='ok'){api=true;$('mode').textContent='全文检索 · BM25 + 词项融合'}}).catch(()=>{});", "draw();$('mode').textContent='在线快照 · 档案、摘要和引用检索';\n}\nstartRadar().catch(err=>{document.getElementById('count').textContent='数据尚未加载';const p=document.createElement('p');p.textContent=err.message+'。请刷新，或通过右上角 GitHub 查看采集运行状态。';document.getElementById('results').append(p)});")
    source = source.replace('>0</strong>', '>—</strong>')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('dist'))
    build(parser.parse_args().out)
