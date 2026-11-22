/* Venta more-info override for Home Assistant built-in Home/Climate views.
 * Narrow interception: only humidifier.venta_aw730.
 */
import "./venta-airwasher-card.js";
const ENTITY="humidifier.venta_aw730";
if(!window.__ventaAirwasherMoreInfoV1){
 window.__ventaAirwasherMoreInfoV1=true;
 let active=null;
 const css=[
  "#venta-mi-overlay{position:fixed;inset:0;z-index:2147482000;background:rgba(10,18,29,.62);display:flex;align-items:center;justify-content:center;padding:12px;box-sizing:border-box}",
  "#venta-mi-window{display:flex;flex-direction:column;max-height:min(96dvh,960px);width:min(620px,100%);min-width:0;overflow:hidden;background:var(--card-background-color,var(--primary-background-color,#fff));color:var(--primary-text-color);border-radius:22px;box-shadow:0 20px 65px #0005}",
  "#venta-mi-header{height:54px;flex:none;display:flex;justify-content:space-between;align-items:center;padding:6px 14px 6px 22px;border-bottom:1px solid var(--divider-color,#ddd);font:600 15px system-ui}",
  "#venta-mi-close{border:0;border-radius:50%;background:var(--secondary-background-color,#f4f5f7);color:var(--primary-text-color);cursor:pointer;font:28px system-ui;width:36px;height:36px;line-height:1}",
  "#venta-mi-content{overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;padding:8px;min-height:0}",
  "#venta-mi-content venta-airwasher-card{display:block}",
  "@media(max-width:600px){#venta-mi-overlay{padding:0;align-items:flex-end}#venta-mi-window{max-height:94dvh;width:100%;border-radius:20px 20px 0 0}#venta-mi-content{padding:4px 0 12px}}"
 ].join("");
 function currentHass(){
  const root=document.querySelector("home-assistant");
  return root?.hass || document.querySelector("home-assistant-main")?.hass || null;
 }
 function close(){
  if(!active)return;
  window.clearInterval(active.timer);
  document.removeEventListener("keydown",active.escape,true);
  active.overlay.remove();
  active=null;
 }
 function show(){
  close();
  const hass=currentHass();
  if(!hass||!customElements.get("venta-airwasher-card"))return false;
  let style=document.getElementById("venta-mi-styles");
  if(!style){
   style=document.createElement("style");style.id="venta-mi-styles";style.textContent=css;document.head.appendChild(style);
  }
  const overlay=document.createElement("div");overlay.id="venta-mi-overlay";overlay.setAttribute("role","presentation");
  const win=document.createElement("section");win.id="venta-mi-window";win.setAttribute("role","dialog");win.setAttribute("aria-modal","true");win.setAttribute("aria-label","Venta AW730");
  const header=document.createElement("header");header.id="venta-mi-header";
  const label=document.createElement("span");label.textContent="Venta AW730";
  const cross=document.createElement("button");cross.type="button";cross.textContent="×";cross.id="venta-mi-close";cross.setAttribute("aria-label","Закрыть");cross.addEventListener("click",close);
  header.append(label,cross);
  const content=document.createElement("div");content.id="venta-mi-content";
  const card=document.createElement("venta-airwasher-card");card.setConfig({entity:ENTITY});card.hass=hass;
  content.append(card);win.append(header,content);overlay.append(win);
  overlay.addEventListener("click",e=>{if(e.target===overlay)close();});
  document.body.append(overlay);
  const escape=e=>{if(e.key==="Escape"){e.preventDefault();close();}};
  document.addEventListener("keydown",escape,true);
  const timer=window.setInterval(()=>{
   if(!document.contains(overlay)){close();return;}
   const h=currentHass();if(h)card.hass=h;
  },1000);
  active={timer,overlay,escape};
  cross.focus({preventScroll:true});
  return true;
 }
 window.addEventListener("hass-more-info",event=>{
  if(event?.detail?.entityId!==ENTITY)return;
  if(!currentHass()||!customElements.get("venta-airwasher-card"))return;
  event.stopImmediatePropagation();
  event.preventDefault();
  try{show();}catch(err){console.error("Venta more-info:",err);close();}
 },true);
}