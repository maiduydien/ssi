(function () {
  "use strict";
  const LINE_KEY = "ssi-iboard-v12-user-lines";
  let lineMode = false;
  let selectedLineId = null;
  let attachedPlot = null;
  let normalizingShapes = false;
  let pendingPoint = null;

  function readLines() {
    try { const v = JSON.parse(localStorage.getItem(LINE_KEY) || "[]"); return Array.isArray(v) ? v : []; }
    catch (_) { return []; }
  }
  function saveLines(lines) { try { localStorage.setItem(LINE_KEY, JSON.stringify(lines)); } catch (_) {} }
  function candles(plot) {
    const trace = (plot.data || []).find(t => t.type === "candlestick" && Array.isArray(t.customdata));
    if (!trace) return [];
    return trace.customdata.map((v, i) => ({x:Number(trace.x[i]), time:Array.isArray(v) ? v[1] : null}));
  }
  function timeAt(plot, x) {
    // Convert any ordinal X coordinate to a timestamp. Unlike nearest-candle
    // snapping, this deliberately extrapolates into the blank area after the
    // latest candle so users can draw/resize lines into future space.
    const cs = candles(plot).filter(c => Number.isFinite(c.x) && c.time && Number.isFinite(Date.parse(c.time)));
    const targetX = Number(x);
    if (!cs.length || !Number.isFinite(targetX)) return null;
    if (cs.length === 1) return new Date(Date.parse(cs[0].time) + (targetX-cs[0].x)*60000).toISOString();
    const interval = (slice) => {
      const diffs=[];
      for(let i=1;i<slice.length;i++) {
        const dx=slice[i].x-slice[i-1].x, dt=Date.parse(slice[i].time)-Date.parse(slice[i-1].time);
        if(dx>0 && dt>0) diffs.push(dt/dx);
      }
      diffs.sort((a,b)=>a-b);
      return diffs.length ? diffs[Math.floor(diffs.length/2)] : 60000;
    };
    if (targetX <= cs[0].x) {
      const step=interval(cs.slice(0,Math.min(cs.length,12)));
      return new Date(Date.parse(cs[0].time)+(targetX-cs[0].x)*step).toISOString();
    }
    const last=cs[cs.length-1];
    if (targetX >= last.x) {
      const step=interval(cs.slice(Math.max(0,cs.length-12)));
      return new Date(Date.parse(last.time)+(targetX-last.x)*step).toISOString();
    }
    let lo=0, hi=cs.length-1;
    while(hi-lo>1){const mid=(lo+hi)>>1;if(cs[mid].x<=targetX)lo=mid;else hi=mid;}
    const a=cs[lo], b=cs[hi], ratio=(targetX-a.x)/(b.x-a.x);
    return new Date(Date.parse(a.time)+ratio*(Date.parse(b.time)-Date.parse(a.time))).toISOString();
  }
  function indexAt(plot, iso) {
    const cs = candles(plot); if (!cs.length || !iso) return null;
    const target = Date.parse(iso);
    const valid = cs.map(c => ({x:c.x, t:Date.parse(c.time)})).filter(c => Number.isFinite(c.t));
    if (!valid.length || !Number.isFinite(target)) return null;
    if (valid.length === 1) return valid[0].x + (target-valid[0].t)/60000;
    // Interpolate between neighboring candle timestamps. Outside the loaded
    // window, extrapolate using a robust typical bar interval so saved lines
    // remain anchored instead of being dropped when the timeframe changes.
    let lo=0, hi=valid.length-1;
    if (target <= valid[0].t) {
      const diffs=[];
      for(let i=1;i<Math.min(valid.length,12);i++){const d=valid[i].t-valid[i-1].t;if(d>0)diffs.push(d);}
      diffs.sort((a,b)=>a-b); const step=diffs.length?diffs[Math.floor(diffs.length/2)]:60000;
      return valid[0].x+(target-valid[0].t)/step;
    }
    if (target >= valid[hi].t) {
      const diffs=[];
      for(let i=Math.max(1,valid.length-11);i<valid.length;i++){const d=valid[i].t-valid[i-1].t;if(d>0)diffs.push(d);}
      diffs.sort((a,b)=>a-b); const step=diffs.length?diffs[Math.floor(diffs.length/2)]:60000;
      return valid[hi].x+(target-valid[hi].t)/step;
    }
    while(hi-lo>1){const mid=(lo+hi)>>1;if(valid[mid].t<=target)lo=mid;else hi=mid;}
    const a=valid[lo], b=valid[hi];
    return a.x+(target-a.t)/(b.t-a.t)*(b.x-a.x);
  }
  function pointAt(plot, event) {
    const full=plot._fullLayout, rect=plot.getBoundingClientRect();
    if(!full||!full.xaxis||!full.yaxis||!full._size) return null;
    const px=event.clientX-rect.left-full._size.l;
    const py=event.clientY-rect.top-full._size.t;
    if(px<0||px>full._size.w||py<0||py>full._size.h) return null;
    try {
      const x=full.xaxis.p2d(px), y=full.yaxis.p2d(py);
      const time=timeAt(plot,x);
      if(!time||!Number.isFinite(Number(y))) return null;
      return {time, price:Number(y)};
    } catch (_) { return null; }
  }
  function currentUserShapes(plot) {
    // User-drawn lines use the data X axis; the live-price guide uses "x domain".
    // This also catches a new Plotly shape before its custom name is normalized.
    return (plot.layout.shapes || []).filter(s => s.type === "line" && s.xref !== "x domain" &&
      s.yref === "y" && Number.isFinite(Number(s.x0)) && Number.isFinite(Number(s.x1)));
  }
  function toShape(line, plot) {
    const x0=indexAt(plot,line.t0), x1=indexAt(plot,line.t1);
    if(x0===null || x1===null) return null;
    return {type:"line", name:"user-line:"+line.id, xref:"x", yref:"y", x0, x1,
      y0:line.y0, y1:line.y1,
      // Keep the line's original appearance; selection is indicated only by endpoint handles.
      line:{color:line.color || "#ffd166",width:Number(line.width)||2,dash:line.dash||"solid"},
      editable:true, layer:"above"};
  }
  function drawSelectedEndpoints(plot) {
    if (!plot || !plot._fullLayout || !plot._fullLayout.xaxis || !plot._fullLayout.yaxis) return;
    const svg=plot.querySelector(".main-svg"); if(!svg)return;
    let overlay=svg.querySelector(".line-selected-endpoints");
    if(!overlay){overlay=document.createElementNS("http://www.w3.org/2000/svg","g");overlay.setAttribute("class","line-selected-endpoints");overlay.style.pointerEvents="none";svg.appendChild(overlay);}
    overlay.innerHTML="";
    const line=readLines().find(l=>l.id===selectedLineId); if(!line)return;
    const full=plot._fullLayout, x0=indexAt(plot,line.t0), x1=indexAt(plot,line.t1); if(x0===null||x1===null)return;
    [[x0,Number(line.y0)],[x1,Number(line.y1)]].forEach(([x,y])=>{
      const cx=full.xaxis.d2p(x)+full._size.l, cy=full.yaxis.d2p(y)+full._size.t;
      const halo=document.createElementNS("http://www.w3.org/2000/svg","circle");
      halo.setAttribute("cx",cx);halo.setAttribute("cy",cy);halo.setAttribute("r","7");halo.setAttribute("fill","#11131c");halo.setAttribute("stroke","#ffffff");halo.setAttribute("stroke-width","2");overlay.appendChild(halo);
      const core=document.createElementNS("http://www.w3.org/2000/svg","circle");
      core.setAttribute("cx",cx);core.setAttribute("cy",cy);core.setAttribute("r","3");core.setAttribute("fill","#ffd166");overlay.appendChild(core);
    });
  }

  function syncShapes(plot) {
    if (!plot || !plot.layout || !plot.data) return;
    const lines=readLines();
    const wanted=lines.map(l=>toShape(l,plot)).filter(Boolean);
    const current=currentUserShapes(plot);
    const signature=a=>JSON.stringify(a.map(s=>({name:s.name,x0:s.x0,x1:s.x1,y0:s.y0,y1:s.y1,line:s.line})).sort((a,b)=>a.name.localeCompare(b.name)));
    if(signature(current)===signature(wanted)) return;
    const keep=(plot.layout.shapes||[]).filter(s=>!(typeof s.name==="string"&&s.name.startsWith("user-line:")));
    // Programmatic redraws (including selection highlighting) must not be
    // mistaken for a user edit and written back over the saved line style.
    normalizingShapes=true;
    window.Plotly.relayout(plot,{shapes:keep.concat(wanted)}).catch(()=>{}).finally(()=>{
      setTimeout(()=>{normalizingShapes=false;},0);
    });
  }
  function styleFromControls() {
    const color=document.getElementById("line-color");
    const style=document.getElementById("line-style");
    const width=document.getElementById("line-width");
    return {color:color?color.value:"#ffd166",dash:style?style.value:"solid",width:width?Number(width.value):2};
  }
  function ensureDrawingOverlay(plot) {
    const svg=plot && plot.querySelector(".main-svg"); if(!svg)return null;
    let overlay=svg.querySelector(".line-drawing-preview-overlay");
    if(!overlay){overlay=document.createElementNS("http://www.w3.org/2000/svg","g");overlay.setAttribute("class","line-drawing-preview-overlay");overlay.style.pointerEvents="none";svg.appendChild(overlay);}
    return overlay;
  }
  function clearDrawingPreview(plot) {
    const overlay=plot && plot.querySelector(".line-drawing-preview-overlay"); if(overlay)overlay.innerHTML="";
  }
  function drawDrawingPreview(plot, event) {
    if(!lineMode || !pendingPoint)return;
    const full=plot._fullLayout, rect=plot.getBoundingClientRect(), overlay=ensureDrawingOverlay(plot);
    if(!full||!full.xaxis||!full.yaxis||!full._size||!overlay)return;
    const px=event.clientX-rect.left-full._size.l, py=event.clientY-rect.top-full._size.t;
    if(px<0||px>full._size.w||py<0||py>full._size.h){overlay.innerHTML="";return;}
    const x0=indexAt(plot,pendingPoint.time);
    if(x0===null)return;
    const x1=full.xaxis.p2d(px), y1=full.yaxis.p2d(py);
    const x0p=full.xaxis.d2p(x0)+full._size.l, y0p=full.yaxis.d2p(pendingPoint.price)+full._size.t;
    const x1p=px+full._size.l, y1p=py+full._size.t;
    overlay.innerHTML="";
    const line=document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",x0p);line.setAttribute("y1",y0p);line.setAttribute("x2",x1p);line.setAttribute("y2",y1p);
    line.setAttribute("stroke",styleFromControls().color||"#ffd166");line.setAttribute("stroke-width",String(Math.max(1,Number(styleFromControls().width)||2)));
    line.setAttribute("stroke-dasharray","6 5");line.setAttribute("stroke-linecap","round");line.setAttribute("opacity","0.9");
    overlay.appendChild(line);
    const marker=document.createElementNS("http://www.w3.org/2000/svg","circle");
    marker.setAttribute("cx",x0p);marker.setAttribute("cy",y0p);marker.setAttribute("r","4");marker.setAttribute("fill",styleFromControls().color||"#ffd166");marker.setAttribute("stroke","#ffffff");marker.setAttribute("stroke-width","1.5");overlay.appendChild(marker);
  }
  function setLineMode(plot, enabled) {
    lineMode=enabled;
    pendingPoint=null;
    clearDrawingPreview(plot);
    const button=document.getElementById("draw-line-toggle");
    if(button){button.classList.toggle("active",enabled);button.textContent=enabled?"Chọn điểm thứ 1… (Esc hủy)":"／";}
    // Reserve blank X-axis space to the right of the latest candle while
    // drawing. Plotly otherwise clips the coordinate system at the last bar,
    // making it impossible to place or drag an endpoint beyond that bar.
    if(window.Plotly && plot) {
      const cs=candles(plot), full=plot._fullLayout;
      const update={dragmode:"pan"};
      if(enabled && cs.length && full && full.xaxis) {
        const xs=cs.map(c=>c.x).filter(Number.isFinite), last=Math.max(...xs);
        const range=full.xaxis.range || [Math.min(...xs)-0.5,last+0.5];
        const step=Math.max(1, Math.round((last-xs[Math.max(0,xs.length-1-10)] || 1)/Math.max(1,Math.min(10,xs.length-1))));
        const pad=Math.max(20,step*20);
        if(Number(range[1]) < last+pad) {
          update["xaxis.range"]=[Number(range[0]),last+pad];
          update["xaxis2.range"]=[Number(range[0]),last+pad];
        }
      }
      window.Plotly.relayout(plot,update).catch(()=>{});
    }
  }
  function closestLine(plot,event) {
    const full=plot._fullLayout, rect=plot.getBoundingClientRect(); if(!full||!full.xaxis||!full.yaxis||!full._size) return null;
    const px=event.clientX-rect.left, py=event.clientY-rect.top;
    let result=null, best=9;
    readLines().forEach(line=>{
      const x0=indexAt(plot,line.t0),x1=indexAt(plot,line.t1); if(x0===null||x1===null)return;
      const ax=full.xaxis.d2p(x0)+full._size.l, bx=full.xaxis.d2p(x1)+full._size.l;
      const ay=full.yaxis.d2p(Number(line.y0))+full._size.t, by=full.yaxis.d2p(Number(line.y1))+full._size.t;
      const dx=bx-ax,dy=by-ay,den=dx*dx+dy*dy;
      const u=den?Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/den)):0;
      const d=Math.hypot(px-(ax+u*dx),py-(ay+u*dy)); if(d<best){best=d;result=line;}
    });
    return result;
  }
  function attachLineTools(plot) {
    if (plot.__v12LineToolsAttached) return;
    plot.__v12LineToolsAttached=true;
    plot.on("plotly_afterplot",()=>{ syncShapes(plot); drawSelectedEndpoints(plot); });
    plot.on("plotly_relayout",event=>{
      if(normalizingShapes) return;
      // Native Plotly Draw Line: persist endpoints as timestamps, not ordinal X indexes.
      const changed=Object.keys(event||{}).some(k=>k==="shapes"||/^shapes\[\d+\]\.(x0|x1|y0|y1|line|name)$/.test(k));
      if(!changed) return;
      const shapes=currentUserShapes(plot), lines=readLines();
      const kept=lines.filter(l=>!shapes.some(s=>s.name==="user-line:"+l.id));
      shapes.forEach(s=>{
        const t0=timeAt(plot,s.x0),t1=timeAt(plot,s.x1); if(!t0||!t1||!Number.isFinite(Number(s.y0))||!Number.isFinite(Number(s.y1)))return;
        let id=(s.name||"").replace("user-line:","");
        if(!id||id==="new"||id==="undefined") id="ln-"+Date.now()+"-"+Math.random().toString(36).slice(2,7);
        const line={id,t0,t1,y0:Number(s.y0),y1:Number(s.y1),color:(s.line||{}).color||"#ffd166",width:Number((s.line||{}).width)||2,dash:(s.line||{}).dash||"solid"};
        kept.push(line); s.name="user-line:"+id;
      });
      saveLines(kept);
      drawSelectedEndpoints(plot);
      // Name shapes so they can be distinguished from the live-price guide.
      const current=(plot.layout.shapes||[]).map(s=>({...s}));
      normalizingShapes=true;
      window.Plotly.relayout(plot,{shapes:current}).catch(()=>{}).finally(()=>{setTimeout(()=>{normalizingShapes=false;},0);});
    });
    // Drag selected line body to move it, or drag either endpoint handle to resize it.
    if(!plot.__lineDragHandlers){
      plot.__lineDragHandlers=true;
      let drag=null;
      plot.addEventListener("pointerdown",event=>{
        if(lineMode || !selectedLineId || event.button!==0)return;
        const full=plot._fullLayout, rect=plot.getBoundingClientRect();
        if(!full||!full.xaxis||!full.yaxis||!full._size)return;
        const line=readLines().find(l=>l.id===selectedLineId); if(!line)return;
        const px=event.clientX-rect.left, py=event.clientY-rect.top;
        const x0=indexAt(plot,line.t0),x1=indexAt(plot,line.t1);if(x0===null||x1===null)return;
        const pts=[
          {which:"start",x:full.xaxis.d2p(x0)+full._size.l,y:full.yaxis.d2p(Number(line.y0))+full._size.t},
          {which:"end",x:full.xaxis.d2p(x1)+full._size.l,y:full.yaxis.d2p(Number(line.y1))+full._size.t}
        ];
        let endpoint=pts.find(p=>Math.hypot(px-p.x,py-p.y)<=12);
        const hit=closestLine(plot,event);
        if(!endpoint && (!hit || hit.id!==selectedLineId))return;
        const point=pointAt(plot,event); if(!point)return;
        drag={id:selectedLineId,which:endpoint?endpoint.which:"body",start:point,original:{...line}};
        plot.setPointerCapture?.(event.pointerId);
        event.preventDefault();event.stopPropagation();
      },true);
      plot.addEventListener("pointermove",event=>{
        if(!drag)return;
        const point=pointAt(plot,event);if(!point)return;
        const lines=readLines(),idx=lines.findIndex(l=>l.id===drag.id);if(idx<0){drag=null;return;}
        const original=drag.original, updated={...original};
        if(drag.which==="start"){updated.t0=point.time;updated.y0=point.price;}
        else if(drag.which==="end"){updated.t1=point.time;updated.y1=point.price;}
        else {
          const dt=Date.parse(point.time)-Date.parse(drag.start.time);
          const dy=point.price-drag.start.price;
          updated.t0=new Date(Date.parse(original.t0)+dt).toISOString();
          updated.t1=new Date(Date.parse(original.t1)+dt).toISOString();
          updated.y0=Number(original.y0)+dy;updated.y1=Number(original.y1)+dy;
        }
        lines[idx]=updated;saveLines(lines);syncShapes(plot);drawSelectedEndpoints(plot);
        event.preventDefault();event.stopPropagation();
      },true);
      const stopDrag=()=>{drag=null;};
      plot.addEventListener("pointerup",stopDrag,true);
      plot.addEventListener("pointercancel",stopDrag,true);
    }
    plot.addEventListener("click",event=>{
      if(lineMode) {
        const point=pointAt(plot,event);
        if(!point) return;
        event.preventDefault(); event.stopPropagation();
        if(typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
        if(!pendingPoint) {
          pendingPoint=point;
          const button=document.getElementById("draw-line-toggle");
          if(button) button.textContent="Chọn điểm thứ 2… (Esc hủy)";
          clearDrawingPreview(plot);
          drawDrawingPreview(plot,event);
        } else {
          const style=styleFromControls();
          const lines=readLines();
          const created={id:"ln-"+Date.now()+"-"+Math.random().toString(36).slice(2,7),
            t0:pendingPoint.time,t1:point.time,y0:pendingPoint.price,y1:point.price,
            color:style.color,width:style.width,dash:style.dash};
          lines.push(created); saveLines(lines); selectedLineId=created.id;
          pendingPoint=null; setLineMode(plot,false); syncShapes(plot);
        }
        return;
      }
      const previousSelected=selectedLineId;
      const hit=closestLine(plot,event);
      selectedLineId=hit?hit.id:null;
      if(previousSelected!==selectedLineId){syncShapes(plot);drawSelectedEndpoints(plot);}
      if(hit) {
        const line=readLines().find(l=>l.id===hit.id);
        if(line) {
          const color=document.getElementById("line-color"), style=document.getElementById("line-style"), width=document.getElementById("line-width");
          if(color) color.value=line.color||"#ffd166";
          if(style) style.value=line.dash||"solid";
          if(width) width.value=String(line.width||2);
        }
        document.querySelectorAll(".draw-line-button").forEach(b=>b.title="Đã chọn line — nhấn Delete để xóa");
      } else {
        document.querySelectorAll(".draw-line-button").forEach(b=>b.title="Bật vẽ line rồi chọn hai điểm trên biểu đồ");
      }
    },true);
  }

  function attachPriceInteractions() {
    const host=document.getElementById("price-chart"); if(!host)return;
    const plot=host.querySelector(".js-plotly-plot"); if(!plot)return;
    if(attachedPlot!==plot){attachedPlot=plot; attachLineTools(plot);}
    let lastPrice=null;
    function axisAt(event) {
      const full=plot._fullLayout,rect=plot.getBoundingClientRect();
      if(!full||!full.yaxis||!full._size)return null;
      const y=event.clientY-rect.top-full._size.t; if(y<0||y>full._size.h)return null;
      try{const value=full.yaxis.p2d(y);return Number.isFinite(value)?value:null;}catch(_){return null;}
    }
    function ensureOverlay(){const svg=plot.querySelector(".main-svg");if(!svg)return null;let overlay=svg.querySelector(".cursor-price-overlay");if(!overlay){overlay=document.createElementNS("http://www.w3.org/2000/svg","g");overlay.setAttribute("class","cursor-price-overlay");overlay.style.pointerEvents="none";svg.appendChild(overlay);}return overlay;}
    function drawCursor(price){const full=plot._fullLayout,overlay=ensureOverlay();if(!full||!overlay||!Number.isFinite(price))return;const y=full.yaxis.d2p(price)+full._size.t,left=full._size.l,width=full._size.w;overlay.innerHTML="";const line=document.createElementNS("http://www.w3.org/2000/svg","line");line.setAttribute("x1",left);line.setAttribute("x2",left+width);line.setAttribute("y1",y);line.setAttribute("y2",y);line.setAttribute("stroke","rgba(225,230,245,0.78)");line.setAttribute("stroke-width","1");line.setAttribute("stroke-dasharray","4 4");overlay.appendChild(line);const text=document.createElementNS("http://www.w3.org/2000/svg","text");text.setAttribute("x",left+width-4);text.setAttribute("y",y-5);text.setAttribute("text-anchor","end");text.setAttribute("fill","#ffffff");text.setAttribute("font-size","11");text.setAttribute("font-weight","600");text.setAttribute("stroke","#08090f");text.setAttribute("stroke-width","2.5");text.setAttribute("paint-order","stroke");text.textContent=Number(price).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});overlay.appendChild(text);}
    function closeMenu(){const menu=document.getElementById("chart-price-context-menu");if(menu)menu.remove();}
    if(!plot.__v12PriceHandlers){plot.__v12PriceHandlers=true;
      plot.addEventListener("mousemove",event=>{const price=axisAt(event);if(price!==null){lastPrice=price;drawCursor(price);}if(lineMode&&pendingPoint)drawDrawingPreview(plot,event);});
      plot.addEventListener("mouseleave",()=>{const overlay=plot.querySelector(".cursor-price-overlay");if(overlay)overlay.innerHTML="";if(lineMode&&pendingPoint)clearDrawingPreview(plot);});
      plot.addEventListener("contextmenu",event=>{const price=axisAt(event),selected=Number.isFinite(price)?price:lastPrice;if(!Number.isFinite(selected))return;event.preventDefault();closeMenu();const value=Number(selected).toFixed(2);const menu=document.createElement("div");menu.id="chart-price-context-menu";menu.style.cssText="position:fixed;z-index:999999;left:"+Math.min(event.clientX,window.innerWidth-230)+"px;top:"+Math.min(event.clientY,window.innerHeight-90)+"px;background:#222130;color:#f5f5fb;border:1px solid #55546a;border-radius:5px;box-shadow:0 4px 14px #0008;padding:5px;min-width:210px;font:12px Arial,sans-serif";const button=document.createElement("button");button.type="button";button.textContent="Copy giá: "+value;button.style.cssText="display:block;width:100%;text-align:left;background:#302f42;color:#fff;border:0;border-radius:3px;padding:9px 10px;cursor:pointer;font:12px Arial,sans-serif";button.addEventListener("click",async()=>{try{if(navigator.clipboard&&navigator.clipboard.writeText)await navigator.clipboard.writeText(value);else{const input=document.createElement("textarea");input.value=value;input.style.position="fixed";input.style.opacity="0";document.body.appendChild(input);input.select();document.execCommand("copy");input.remove();}button.textContent="Đã copy: "+value;setTimeout(closeMenu,900);}catch(_){button.textContent="Không copy được: "+value;}});menu.appendChild(button);document.body.appendChild(menu);const dismiss=e=>{if(!menu.contains(e.target)){closeMenu();document.removeEventListener("mousedown",dismiss,true);}};setTimeout(()=>document.addEventListener("mousedown",dismiss,true),0);});
    }
  }
  function wireControls(){
    const draw=document.getElementById("draw-line-toggle"), del=document.getElementById("delete-line");
    if(draw&&!draw.__wired){draw.__wired=true;draw.addEventListener("click",()=>{const plot=attachedPlot;if(plot)setLineMode(plot,!lineMode);});}
    ["line-color","line-style","line-width"].forEach(id=>{const el=document.getElementById(id);if(el&&!el.__wired){el.__wired=true;el.addEventListener("change",()=>{if(attachedPlot){window.Plotly.relayout(attachedPlot,{"newshape.line":styleFromControls()}).catch(()=>{});if(selectedLineId){const l=readLines(),line=l.find(x=>x.id===selectedLineId);if(line){Object.assign(line,styleFromControls());saveLines(l);syncShapes(attachedPlot);}}}});}});
    if(del&&!del.__wired){del.__wired=true;del.addEventListener("click",()=>{if(!selectedLineId)return;saveLines(readLines().filter(l=>l.id!==selectedLineId));selectedLineId=null;if(attachedPlot){syncShapes(attachedPlot);drawSelectedEndpoints(attachedPlot);}});}
  }
  document.addEventListener("keydown",event=>{
    if(event.key==="Escape"&&lineMode){setLineMode(attachedPlot,false);return;}
    if((event.key==="Delete"||event.key==="Backspace")&&selectedLineId){const active=document.activeElement;if(active&&["INPUT","TEXTAREA","SELECT"].includes(active.tagName))return;event.preventDefault();saveLines(readLines().filter(l=>l.id!==selectedLineId));selectedLineId=null;if(attachedPlot){syncShapes(attachedPlot);drawSelectedEndpoints(attachedPlot);}}
  });
  const observer=new MutationObserver(()=>{attachPriceInteractions();wireControls();});
  function start(){observer.observe(document.body,{childList:true,subtree:true});attachPriceInteractions();wireControls();}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);else start();
})();

/* V14: draggable trade dialogs (LONG/SHORT market confirm, edit/cancel, close/reverse). */
(function () {
  "use strict";
  function makeDialogDraggable(card) {
    if (!card || card.dataset.dragReady === "1") return;
    const handle = card.querySelector("h4");
    if (!handle) return;
    card.dataset.dragReady = "1";
    handle.style.cursor = "move";
    handle.style.userSelect = "none";
    handle.title = "Giữ và kéo để di chuyển hộp thoại";
    let dragging = false, startX = 0, startY = 0, startLeft = 0, startTop = 0;
    handle.addEventListener("pointerdown", function (event) {
      if (event.button !== 0) return;
      const overlay = card.closest(".trade-modal-overlay");
      if (!overlay || getComputedStyle(overlay).display === "none") return;
      const rect = card.getBoundingClientRect();
      // Convert the centered flex card to an explicitly positioned draggable card.
      card.style.position = "fixed";
      card.style.margin = "0";
      card.style.transform = "none";
      card.style.left = rect.left + "px";
      card.style.top = rect.top + "px";
      card.style.maxHeight = "calc(100vh - 24px)";
      card.style.overflowY = "auto";
      startX = event.clientX; startY = event.clientY;
      startLeft = rect.left; startTop = rect.top;
      dragging = true;
      handle.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    handle.addEventListener("pointermove", function (event) {
      if (!dragging) return;
      const maxLeft = Math.max(0, window.innerWidth - card.offsetWidth);
      const maxTop = Math.max(0, window.innerHeight - card.offsetHeight);
      card.style.left = Math.min(maxLeft, Math.max(0, startLeft + event.clientX - startX)) + "px";
      card.style.top = Math.min(maxTop, Math.max(0, startTop + event.clientY - startY)) + "px";
    });
    const stop = function () { dragging = false; };
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
  }
  function wireTradeDialogs() {
    document.querySelectorAll(".trade-modal-overlay .trade-modal-card").forEach(makeDialogDraggable);
  }
  const dialogObserver = new MutationObserver(wireTradeDialogs);
  function startDialogDrag() {
    if (document.body) dialogObserver.observe(document.body, {childList:true, subtree:true});
    wireTradeDialogs();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", startDialogDrag);
  else startDialogDrag();
})();
