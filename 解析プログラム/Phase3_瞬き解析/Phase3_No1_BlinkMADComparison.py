#!/usr/bin/env python3
"""Create self-contained QC HTML comparing blink detections at MAD k=8, 10, and 12."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

MAIN_SCRIPT = Path(__file__).with_name("Phase3_No1_BlinkRate.py")
SPEC = importlib.util.spec_from_file_location("phase3_blink_rate", MAIN_SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {MAIN_SCRIPT}")
blink = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = blink
SPEC.loader.exec_module(blink)


def save_comparison_html(results: dict[int, object], path: Path) -> None:
    reference = results[10]
    segments = []
    for set_number in range(1, blink.N_SETS + 1):
        signal = reference.sets.get(set_number)
        if signal is None:
            segments.append({"set": set_number, "missing": True})
            continue
        segments.append(
            {
                "set": set_number,
                "missing": False,
                "values": blink._encoded_float32(signal.filtered_uv["Fp1_Fp2_mean"]),
                "peaks": {
                    str(k): results[k].sets[set_number].peaks["Fp1_Fp2_mean"].tolist()
                    for k in (8, 10, 12)
                },
            }
        )
    payload = {
        "session": reference.session_id,
        "sfreq": blink.SFREQ,
        "segments": segments,
        "thresholds": {
            str(k): results[k].thresholds["Fp1_Fp2_mean"]["prominence_uv"]
            for k in (8, 10, 12)
        },
    }
    html = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>MAD comparison QC</title>
<style>body{font-family:Arial,sans-serif;margin:16px;color:#202124}.tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}button{padding:6px 12px}canvas{border:1px solid #777;width:100%;height:620px;cursor:grab;touch-action:none}.legend{margin:8px 0}.m{font-size:22px;margin-right:5px}.k8{color:#D1495B}.k10{color:#F28E2B}.k12{color:#2A9D8F}.hint{color:#555}</style></head><body>
<h1>ID__SESSION__: MAD multiplier comparison</h1><div class="legend"><span class="m k12">○</span>k=12 retained &nbsp; <span class="m k10">○</span>added at k=10 &nbsp; <span class="m k8">○</span>added at k=8</div>
<div class="tools"><button id="xin">x zoom in</button><button id="xout">x zoom out</button><button id="yin">y zoom in</button><button id="yout">y zoom out</button><button id="reset">Reset</button><button class="setjump" data-set="1">Set 1</button><button class="setjump" data-set="2">Set 2</button><button class="setjump" data-set="3">Set 3</button><button class="setjump" data-set="4">Set 4</button><button class="setjump" data-set="5">Set 5</button><button class="setjump" data-set="6">Set 6</button><span id="status"></span></div>
<p class="hint">Markers are mutually exclusive. Thus orange means detected at k=10 but not k=12; red means detected at k=8 but not k=10. Drag or use Left/Right Arrow to move.</p>
<canvas id="plot" width="1700" height="620"></canvas><script id="payload" type="application/json">__PAYLOAD__</script><script>"use strict";const P=JSON.parse(document.getElementById('payload').textContent);function dec(s){const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new Float32Array(u.buffer)}P.segments.forEach(s=>{if(!s.missing){s.values=dec(s.values);for(const k of ['8','10','12'])s.peaks[k]=new Set(s.peaks[k])}});const cv=document.getElementById('plot'),c=cv.getContext('2d'),L=90,R=25,T=30,B=65;let x0=0,x1=600,drag=null,timer=null,all=[];P.segments.forEach(s=>{if(!s.missing)for(const v of s.values)if(Number.isFinite(v))all.push(Math.abs(v))});all.sort((a,b)=>a-b);let baseY=Math.max(10,all[Math.floor(all.length*.995)]*1.25),ys=baseY;function clamp(a,b){const sp=Math.max(2,Math.min(600,b-a));a=Math.max(0,Math.min(600-sp,a));return[a,a+sp]}function zoom(f,r=.5){const q=x0+r*(x1-x0),sp=(x1-x0)*f;[x0,x1]=clamp(q-r*sp,q+(1-r)*sp);draw()}function pan(d){const z=(x1-x0)*.05*d;[x0,x1]=clamp(x0+z,x1+z);draw()}function stop(){if(timer){clearInterval(timer);timer=null}}function start(d){stop();pan(d);timer=setInterval(()=>pan(d),80)}function xy(p,v,w,h){return[L+(p-x0)/(x1-x0)*w,T+h/2-v/ys*h*.43]}function draw(){c.clearRect(0,0,cv.width,cv.height);const w=cv.width-L-R,h=cv.height-T-B;c.strokeStyle='#222';c.strokeRect(L,T,w,h);c.font='16px Arial';c.fillStyle='#111';c.textAlign='center';for(let t=Math.ceil(x0/50)*50;t<=x1;t+=50){const x=L+(t-x0)/(x1-x0)*w;c.strokeStyle='#ddd';c.beginPath();c.moveTo(x,T);c.lineTo(x,T+h);c.stroke();c.fillStyle='#111';c.fillText(String(t),x,T+h+25)}for(let s=1;s<6;s++){const p=s*100;if(p<x0||p>x1)continue;const x=L+(p-x0)/(x1-x0)*w;c.strokeStyle='#999';c.setLineDash([6,5]);c.beginPath();c.moveTo(x,T);c.lineTo(x,T+h);c.stroke();c.setLineDash([])}for(let s=1;s<=6;s++){const p=(s-.5)*100;if(p>=x0&&p<=x1)c.fillText('Set '+s,L+(p-x0)/(x1-x0)*w,T+20)}P.segments.forEach(seg=>{if(seg.missing)return;const st=(seg.set-1)*100,n=seg.values.length;c.strokeStyle='#3268A8';c.lineWidth=1;c.beginPath();const pc=Math.max(1,Math.floor(w*2));for(let px=0;px<pc;px++){const pa=x0+(x1-x0)*px/pc,pb=x0+(x1-x0)*(px+1)/pc;if(pb<st||pa>st+100)continue;const a=Math.max(0,Math.floor((pa-st)/100*n)),b=Math.min(n,Math.max(a+1,Math.ceil((pb-st)/100*n)));let lo=Infinity,hi=-Infinity;for(let i=a;i<b;i++){lo=Math.min(lo,seg.values[i]);hi=Math.max(hi,seg.values[i])}if(!Number.isFinite(lo))continue;const x=L+px/pc*w;c.moveTo(x,xy(pa,lo,w,h)[1]);c.lineTo(x,xy(pa,hi,w,h)[1])}c.stroke();for(let i=0;i<n;i++){let col=null,rad=0;if(seg.peaks['12'].has(i)){col='#2A9D8F';rad=6}else if(seg.peaks['10'].has(i)){col='#F28E2B';rad=5}else if(seg.peaks['8'].has(i)){col='#D1495B';rad=4}else continue;const p=st+i/Math.max(1,n-1)*100;if(p<x0||p>x1)continue;const [x,y]=xy(p,seg.values[i],w,h);c.strokeStyle=col;c.lineWidth=2;c.beginPath();c.arc(x,y,rad,0,Math.PI*2);c.stroke()}});c.fillStyle='#111';c.font='20px Arial';c.fillText('Experimental Progress, %',L+w/2,cv.height-10);c.save();c.translate(22,T+h/2);c.rotate(-Math.PI/2);c.fillText('Filtered amplitude (µV)',0,0);c.restore();document.getElementById('status').textContent=`x ${x0.toFixed(1)}–${x1.toFixed(1)} %, y ±${ys.toFixed(1)} µV | thresholds: k8 ${P.thresholds['8'].toFixed(1)}, k10 ${P.thresholds['10'].toFixed(1)}, k12 ${P.thresholds['12'].toFixed(1)} µV`}
document.getElementById('xin').onclick=()=>zoom(.5);document.getElementById('xout').onclick=()=>zoom(2);document.getElementById('yin').onclick=()=>{ys=Math.max(.1,ys/1.5);draw()};document.getElementById('yout').onclick=()=>{ys*=1.5;draw()};document.getElementById('reset').onclick=()=>{x0=0;x1=600;ys=baseY;draw()};document.querySelectorAll('.setjump').forEach(b=>b.onclick=()=>{const s=Number(b.dataset.set);x0=(s-1)*100;x1=s*100;draw()});document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();start(e.key==='ArrowLeft'?-1:1)}});document.addEventListener('keyup',e=>{if(e.key.startsWith('Arrow'))stop()});window.addEventListener('blur',stop);cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect(),q=(e.clientX-r.left)/r.width;zoom(e.deltaY>0?1.5:.67,Math.max(0,Math.min(1,q)))},{passive:false});cv.addEventListener('pointerdown',e=>{cv.setPointerCapture(e.pointerId);drag={x:e.clientX,a:x0,b:x1};cv.style.cursor='grabbing'});cv.addEventListener('pointerup',()=>{drag=null;cv.style.cursor='grab'});cv.addEventListener('pointermove',e=>{if(!drag)return;const r=cv.getBoundingClientRect(),d=(e.clientX-drag.x)/r.width*(drag.b-drag.a);[x0,x1]=clamp(drag.a-d,drag.b-d);draw()});draw();</script></body></html>'''
    html = html.replace("__SESSION__", reference.session_id).replace(
        "__PAYLOAD__", json.dumps(payload, separators=(",", ":"))
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", action="append", type=blink.parse_participant, required=True)
    parser.add_argument("--input-root", type=Path, default=blink.DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=blink.DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    output = (
        args.output_root
        / "Phase3_瞬き解析"
        / "No1_BlinkRate_ParameterComparison"
        / "ComparisonHTML"
    )
    for participant in args.participant:
        product_dir = blink.normalize_product(participant.product)[0]
        for session_id in (participant.first_session_id, participant.second_session_id):
            condition = "Eye Drop" if session_id == participant.drops_session_id else "Control"
            results = {
                k: blink.detect_session(session_id, args.input_root, condition, float(k))
                for k in (8, 10, 12)
            }
            save_comparison_html(
                results,
                output / product_dir / f"ID{session_id}_No1_MAD08_10_12_Comparison.html",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
