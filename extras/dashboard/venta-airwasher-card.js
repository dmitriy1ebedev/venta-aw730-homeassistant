class VentaAirwasherCard extends HTMLElement {
  constructor(){
    super();
    this.attachShadow({mode:"open"});
    this._config=null;
    this._hass=null;
    this._mounted=false;
    this._sending=false;
  }
  static getStubConfig(){return {entity:"humidifier.venta_aw730"};}
  getCardSize(){return 7;}
  setConfig(config){
    if(!config || typeof config.entity!=="string" || !config.entity.startsWith("humidifier.")) throw Error("Укажите entity: humidifier...");
    this._config={
      entity:config.entity,
      humidity:config.humidity||"sensor.venta_aw730_humidity",
      temperature:config.temperature||"sensor.venta_aw730_temperature",
      fan:config.fan||"select.venta_aw730_fan_speed",
      led:config.led||"switch.venta_aw730_led_on",
      color:config.led_color||"select.venta_aw730_led_color",
      brightness:config.led_brightness||"select.venta_aw730_led_brightness"
    };
    if(!this._mounted) this._mount();
  }
  set hass(value){this._hass=value;if(this._config&&!this._mounted)this._mount();if(this._mounted)this._sync();}
  _node(name){return this.shadowRoot.querySelector('[data-ui="'+name+'"]');}
  _entity(id){return this._hass&&this._hass.states[id];}
  _value(id){const s=this._entity(id);return !s||s.state==="unknown"||s.state==="unavailable"?null:s.state;}
  _mount(){
    this._mounted=true;
    const colors=[["purple","#a87de4"],["blue","#4a9de8"],["green","#33ab78"],["light green","#9dc36a"],["lemon","#e1d96d"],["yellow","#eac052"],["orange","#eb9845"],["AQI","linear-gradient(120deg,#33ab78,#4a9de8,#a87de4)"]];
    const style=[
      ":host{display:block;--venta-accent:var(--accent-color,#557bd3)}",
      "ha-card{background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color);border-radius:22px;padding:22px;max-width:720px;margin:0 auto;box-sizing:border-box;overflow:hidden}",
      "button,input{font:inherit}button{cursor:pointer;-webkit-tap-highlight-color:transparent}button:disabled,input:disabled{opacity:.45;cursor:not-allowed}",
      ".top{display:flex;align-items:center;justify-content:space-between;gap:14px}",
      ".eyebrow{font-size:11px;text-transform:uppercase;font-weight:750;letter-spacing:.1em;opacity:.65}",
      ".heading{font-size:23px;font-weight:760;margin-top:5px;letter-spacing:-.025em}",
      ".subtext{font-size:13px;opacity:.65;margin-top:5px}",
      ".power{border:none;border-radius:17px;width:58px;height:58px;background:var(--secondary-background-color,#f3f4f7);color:var(--primary-text-color);flex-shrink:0}",
      ".power.on{background:var(--venta-accent);color:#fff}.power ha-icon{--mdc-icon-size:28px}",
      ".metrics{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:19px 0 18px}",
      ".metric{padding:15px;border-radius:16px;background:var(--secondary-background-color,#f3f4f7)}",
      ".metriclabel{font-size:12px;opacity:.7}.metricval{font-size:30px;font-weight:760;margin-top:7px;line-height:1.12;letter-spacing:-.03em}",
      ".metricunit{font-size:17px;opacity:.65;margin-left:2px}",
      ".block{border-top:1px solid var(--divider-color,rgba(125,125,125,.22));padding:17px 0}",
      ".block.last{padding-bottom:0}.line{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}",
      ".label{font-size:15px;font-weight:700}.muted{font-size:12px;opacity:.6}",
      ".target{font-size:18px;font-weight:760;font-variant-numeric:tabular-nums}",
      "input[type=range]{accent-color:var(--venta-accent);width:100%;margin:5px 0}",
      ".rangelabels{display:flex;justify-content:space-between;font-size:11px;opacity:.6}",
      ".buttons{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}",
      ".buttons.five{grid-template-columns:repeat(5,minmax(0,1fr))}",
      ".seg{border:1px solid var(--divider-color,rgba(120,120,120,.2));border-radius:12px;background:var(--secondary-background-color,#f3f4f7);color:var(--primary-text-color);padding:10px 2px;font-size:13px;font-weight:650;min-width:0}",
      ".seg.active{background:var(--venta-accent);border-color:var(--venta-accent);color:#fff}",
      ".ledtoggle{width:47px;height:28px;padding:3px;border:0;border-radius:40px;background:var(--disabled-text-color,#aaa);display:flex;align-items:center}",
      ".ledtoggle span{width:22px;height:22px;background:white;border-radius:100%;transition:transform .15s;box-shadow:0 1px 3px #0002}",
      ".ledtoggle.on{background:var(--venta-accent)}.ledtoggle.on span{transform:translateX(19px)}",
      ".colors{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}",
      ".colorbtn{width:32px;height:32px;border-radius:100%;background:transparent;border:2px solid transparent;padding:3px;display:grid;place-items:center}",
      ".colorbtn span{display:block;width:22px;height:22px;border-radius:100%;box-shadow:inset 0 0 0 1px #5554}",
      ".colorbtn.active{border-color:var(--venta-accent)}",
      ".brightness{display:flex;gap:11px;align-items:center;font-size:12px}.brightness input{flex:1}",
      ".msg{font-size:12px;min-height:14px;margin-top:12px;opacity:.68}.msg.error{color:var(--error-color,#c44);opacity:1}",
      ".adjustments{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;border-top:1px solid var(--divider-color,rgba(120,120,120,.18))}",
      ".adjustments .block{min-width:0;border-top:0;padding:15px 0 16px}.adjustments .line{min-height:40px;margin-bottom:11px;align-items:flex-start}.adjustments .label{font-size:13px}.adjustments .target{font-size:17px}.adjustments .muted{font-size:11px}",
      ".adjustments .buttons.five{gap:3px}.adjustments .seg{padding:10px 0;font-size:12px;border-radius:9px}",
      ".adjustments .rangelabels{font-size:11px}.colors{justify-content:space-between}",
      "@media(max-width:420px){ha-card{padding:17px;border-radius:18px}.heading{font-size:21px}.power{width:52px;height:52px}.metric{padding:13px}.metricval{font-size:27px}.adjustments{gap:9px}.adjustments .seg{font-size:11px}.adjustments .label{font-size:12px}}"
    ].join("");
    const colorButtons=colors.map(x=>'<button type="button" class="colorbtn" data-color="'+x[0]+'" title="'+x[0]+'"><span style="background:'+x[1]+'"></span></button>').join("");
    const speedButtons=[1,2,3,4,5].map(n=>'<button type="button" class="seg" data-fan="'+n+'">'+n+'</button>').join("");
    const html=[
      '<ha-card><div class="top"><div><div class="eyebrow">Venta AW730</div><div class="heading">Venta AW730</div><div class="subtext" data-ui="status">Загрузка…</div></div>',
      '<button type="button" class="power" data-action="power" title="Включить/выключить" aria-label="Питание"><ha-icon icon="mdi:power"></ha-icon></button></div>',
      '<div class="metrics"><div class="metric"><div class="metriclabel">Влажность</div><div class="metricval"><span data-ui="humidity">—</span><span class="metricunit">%</span></div></div>',
      '<div class="metric"><div class="metriclabel">Температура</div><div class="metricval"><span data-ui="temperature">—</span><span class="metricunit">°C</span></div></div></div>',
      '<div class="block"><div class="line"><span class="label">Целевая влажность</span><span class="target"><span data-ui="target">55</span>%</span></div>',
      '<input type="range" min="30" max="70" value="55" step="1" data-action="target" aria-label="Целевая влажность">',
      '<div class="rangelabels"><span>30%</span><span>70%</span></div></div>',
      '<div class="block"><div class="line"><span class="label">Режим</span></div><div class="buttons">',
      '<button type="button" class="seg" data-mode="Auto">Авто</button><button type="button" class="seg" data-mode="Manual">Ручной</button><button type="button" class="seg" data-mode="Sleep">Ночной</button></div></div>',
      '<div class="block"><div class="line"><span class="label">Скорость вентилятора</span><span class="muted">1–5</span></div><div class="buttons five">'+speedButtons+'</div></div>',
      '<div class="block last"><div class="line"><div><div class="label">LED-подсветка</div><div class="muted">Цвет и яркость</div></div>',
      '<button type="button" class="ledtoggle" data-action="led" title="Подсветка" aria-label="Включить подсветку"><span></span></button></div>',
      '<div class="colors">'+colorButtons+'</div>',
      '<div class="brightness"><span>Яркость</span><input type="range" min="1" max="8" step="1" data-action="brightness" aria-label="Яркость подсветки"><b data-ui="brightness">—</b></div></div>',
      '<div class="msg" data-ui="message" role="status" aria-live="polite"></div></ha-card>'
    ].join("");
    this.shadowRoot.innerHTML="<style>"+style+"</style>"+html;
    // Current humidity + temperature stay in one row; target + fan speed share another.
    // Move already-rendered blocks, keeping their existing service handlers intact.
    const targetBlock=this.shadowRoot.querySelector('[data-action="target"]').closest(".block");
    const speedBlock=this.shadowRoot.querySelector("[data-fan]").closest(".block");
    const adjustments=document.createElement("div");
    adjustments.className="adjustments";
    targetBlock.before(adjustments);
    adjustments.append(targetBlock,speedBlock);
    this.shadowRoot.addEventListener("click",e=>{
      const b=e.target.closest("[data-action],[data-mode],[data-fan],[data-color]");
      if(!b||!this._hass||this._sending)return;
      const c=this._config;
      if(b.dataset.action==="power"){
        this._call("humidifier",this._value(c.entity)==="on"?"turn_off":"turn_on",{entity_id:c.entity});
      }else if(b.dataset.action==="led"){
        this._call("switch",this._value(c.led)==="on"?"turn_off":"turn_on",{entity_id:c.led});
      }else if(b.dataset.mode){
        this._call("humidifier","set_mode",{entity_id:c.entity,mode:b.dataset.mode});
      }else if(b.dataset.fan){
        this._call("select","select_option",{entity_id:c.fan,option:b.dataset.fan});
      }else if(b.dataset.color){
        this._call("select","select_option",{entity_id:c.color,option:b.dataset.color});
      }
    });
    const target=this.shadowRoot.querySelector('[data-action="target"]');
    target.addEventListener("input",e=>{this._node("target").textContent=e.target.value;});
    target.addEventListener("change",e=>{this._call("humidifier","set_humidity",{entity_id:this._config.entity,humidity:Number(e.target.value)});});
    const brightness=this.shadowRoot.querySelector('[data-action="brightness"]');
    brightness.addEventListener("input",e=>{this._node("brightness").textContent=e.target.value;});
    brightness.addEventListener("change",e=>{this._call("select","select_option",{entity_id:this._config.brightness,option:String(e.target.value)});});
  }
  async _call(domain,service,data){
    this._sending=true;const msg=this._node("message");msg.classList.remove("error");msg.textContent="Применение…";
    try{await this._hass.callService(domain,service,data);msg.textContent="";}
    catch(e){msg.textContent="Команда не выполнена: "+String(e&&e.message||"ошибка связи").slice(0,90);msg.classList.add("error");}
    finally{this._sending=false;}
  }
  _sync(){
    const c=this._config;
    const h=this._entity(c.entity);
    const available=!!h&&h.state!=="unavailable"&&h.state!=="unknown";
    const on=h&&h.state==="on";
    const humidity=this._value(c.humidity)??h?.attributes?.current_humidity;
    const temp=this._value(c.temperature);
    this._node("humidity").textContent=humidity??"—";
    this._node("temperature").textContent=temp??"—";
    this._node("status").textContent=!available?"Нет связи":on?"Работает":"Выключена";
    const power=this.shadowRoot.querySelector('[data-action="power"]');
    power.classList.toggle("on",!!on);power.disabled=!available;power.setAttribute("aria-pressed",String(!!on));
    const t=Number(h?.attributes?.humidity??55);
    const slider=this.shadowRoot.querySelector('[data-action="target"]');
    if(Number.isFinite(t)&&t>=30&&t<=70&&this.shadowRoot.activeElement!==slider){
      slider.value=String(t);this._node("target").textContent=t;
    }
    this.shadowRoot.querySelectorAll("[data-mode]").forEach(b=>{b.classList.toggle("active",b.dataset.mode===h?.attributes?.mode);b.disabled=!available;});
    const fan=this._value(c.fan);
    this.shadowRoot.querySelectorAll("[data-fan]").forEach(b=>{b.classList.toggle("active",b.dataset.fan===fan);b.disabled=!available||fan===null;});
    const led=this._value(c.led);
    const ledToggle=this.shadowRoot.querySelector('[data-action="led"]');
    ledToggle.classList.toggle("on",led==="on");ledToggle.disabled=led===null;ledToggle.setAttribute("aria-pressed",String(led==="on"));
    const color=this._value(c.color);
    this.shadowRoot.querySelectorAll("[data-color]").forEach(b=>{b.classList.toggle("active",b.dataset.color===color);b.disabled=color===null;});
    const b=this._value(c.brightness);
    const brightness=this.shadowRoot.querySelector('[data-action="brightness"]');
    brightness.disabled=b===null;
    if(b!==null&&this.shadowRoot.activeElement!==brightness){brightness.value=b;this._node("brightness").textContent=b;}
  }
}
if(!customElements.get("venta-airwasher-card"))customElements.define("venta-airwasher-card",VentaAirwasherCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(x=>x.type==="venta-airwasher-card")){
  window.customCards.push({type:"venta-airwasher-card",name:"Venta AW730",description:"Управление мойкой воздуха в одной карточке"});
}
