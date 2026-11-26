class VentaAirwasherCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._config = null;
    this._hass = null;
    this._sending = false;
  }

  static getStubConfig() { return {entity: "humidifier.venta_aw730"}; }
  getCardSize() { return 7; }

  setConfig(config) {
    if (!config || typeof config.entity !== "string" ||
        !/^humidifier\.[a-z0-9_]+$/.test(config.entity)) {
      throw Error("Specify a humidifier entity");
    }
    // Preserve the original AW730 defaults ONLY for the original entity.
    // Never implicitly attach a different humidifier to the first device's helpers.
    const prefix = config.entity === "humidifier.venta_aw730" ? "venta_aw730" : null;
    const role = (key, domain, suffix) => {
      const id = Object.hasOwn(config, key) ? config[key] :
        prefix && suffix ? domain + "." + prefix + "_" + suffix : null;
      if (id === null || id === false || id === undefined) return null;
      if (typeof id !== "string" ||
          !new RegExp("^" + domain + "\\.[a-z0-9_]+$").test(id)) {
        throw Error("Invalid " + key + " entity");
      }
      return id;
    };
    this._config = {
      entity: config.entity,
      humidity: role("humidity", "sensor", "humidity"),
      temperature: role("temperature", "sensor", "temperature"),
      fan: role("fan", "select", "fan_speed"),
      led: role("led", "switch", "led_on"),
      color: role("led_color", "select", "led_color"),
      brightness: role("led_brightness", "select", "led_brightness"),
      pm25: role("pm25", "sensor", null),
      water: role("water_level", "sensor", null)
    };
    if (!this._mounted) this._mount();
    this._sync();
  }

  set hass(value) {
    this._hass = value;
    if (this._mounted) this._sync();
  }

  _node(name) { return this.shadowRoot.querySelector('[data-ui="' + name + '"]'); }
  _entity(id) { return id ? this._hass?.states?.[id] : null; }
  _value(id) {
    const state = this._entity(id)?.state;
    return state == null || state === "unknown" || state === "unavailable" ? null : state;
  }
  _hasService(domain, service) {
    return typeof this._hass?.callService === "function" &&
      Object.hasOwn(this._hass.services?.[domain] || {}, service);
  }
  _choices(id, attribute) {
    const values = this._entity(id)?.attributes?.[attribute];
    return Array.isArray(values) ? values : [];
  }
  _ready() {
    return !this._sending && ["on", "off"].includes(this._value(this._config.entity));
  }

  // Revalidate current state, role, domain, service and option at dispatch time.
  // This also rejects synthetic events on disabled controls and duplicate clicks.
  _allowed(domain, service, data) {
    const c = this._config;
    if (!c || !this._ready() || !this._hasService(domain, service)) return false;
    const id = data.entity_id;
    if (this._value(id) === null) return false;
    if (domain === "humidifier" && id === c.entity) {
      if (service === "turn_on" || service === "turn_off") return true;
      if (service === "set_mode") {
        return ["Auto", "Manual", "Sleep"].includes(data.mode) &&
          this._choices(id, "available_modes").includes(data.mode);
      }
      if (service === "set_humidity") {
        const n = data.humidity, a = this._entity(id)?.attributes || {};
        const min = Number(a.min_humidity ?? 30), max = Number(a.max_humidity ?? 70);
        return Number.isInteger(n) && n >= 30 && n <= 70 && n >= min && n <= max;
      }
    }
    if (domain === "switch" && id === c.led) {
      return ["turn_on", "turn_off"].includes(service) && ["on", "off"].includes(this._value(id));
    }
    if (domain === "select" && [c.fan, c.color, c.brightness].includes(id)) {
      return service === "select_option" && typeof data.option === "string" &&
        this._choices(id, "options").includes(data.option);
    }
    return false;
  }

  _mount() {
    this._mounted = true;
    const colors = [["purple","#a87de4"],["blue","#4a9de8"],["green","#33ab78"],
      ["light green","#9dc36a"],["lemon","#e1d96d"],["yellow","#eac052"],
      ["orange","#eb9845"],["AQI","linear-gradient(120deg,#33ab78,#4a9de8,#a87de4)"]];
    this.shadowRoot.innerHTML = '<style>' +
      ':host{display:block;container-type:inline-size;--venta-accent:var(--accent-color,#557bd3)}' +
      'ha-card{display:block;box-sizing:border-box;padding:18px;max-width:720px;margin:0 auto;border-radius:18px;background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color,#202124)}' +
      '[hidden]{display:none!important}button,input{font:inherit}button{cursor:pointer;min-height:44px;color:inherit}button:disabled,input:disabled{opacity:.45;cursor:not-allowed}' +
      'button:focus-visible,input:focus-visible{outline:3px solid var(--venta-accent);outline-offset:3px}' +
      '.top,.line{display:flex;align-items:center;justify-content:space-between;gap:12px}.heading{font-size:22px;font-weight:700}.subtext{font-size:14px;margin-top:5px}' +
      '.power,.seg,.colorbtn{border:1px solid var(--divider-color,#aaa);border-radius:12px;background:var(--secondary-background-color,#eee);padding:8px}.power{min-width:52px;font-size:21px}' +
      'button[aria-pressed="true"]{border:2px solid var(--venta-accent);font-weight:750;box-shadow:inset 0 -3px var(--venta-accent)}' +
      '.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,125px),1fr));gap:8px;margin:16px 0}.metric{min-width:0;padding:12px;border-radius:12px;background:var(--secondary-background-color,#eee)}.metricval{font-size:24px;font-weight:700;overflow-wrap:anywhere}.metricunit{font-size:14px}' +
      '.block{border-top:1px solid var(--divider-color,#bbb);padding:14px 0}.label{font-size:15px;font-weight:650}.target{font-weight:700}.buttons{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:8px}.buttons.five{grid-template-columns:repeat(5,minmax(0,1fr))}.seg{min-width:0;padding:6px 2px}' +
      'input[type=range]{width:100%;box-sizing:border-box;accent-color:var(--venta-accent);min-height:44px}.range{display:flex;justify-content:space-between;font-size:12px}.adjustments{display:grid;grid-template-columns:1fr 1fr;gap:14px}.adjustments .block{min-width:0}.colors{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}.colorbtn{width:44px;height:44px;padding:6px}.colorbtn span{display:block;width:22px;height:22px;border-radius:50%;margin:auto;border:1px solid #777}' +
      '.msg{min-height:20px;font-size:13px}.msg.error{color:var(--error-color,#a22)}@container (max-width:450px){.adjustments{grid-template-columns:1fr}ha-card{padding:12px}.metricval{font-size:22px}}' +
      '</style>' +
      '<ha-card><div class="top"><div><div class="heading">Venta AW730</div><div class="subtext" data-ui="status" role="status">Загрузка…</div></div>' +
      '<button type="button" class="power" data-action="power" aria-label="Питание" aria-pressed="false" disabled>⏻</button></div>' +
      '<div class="metrics">' +
      ['humidity','temperature','pm25','water'].map((key,i) =>
        '<div class="metric" data-ui="' + key + '-tile"><div>' + ['Влажность','Температура','PM2.5','Уровень воды'][i] +
        '</div><div class="metricval"><span data-ui="' + key + '">—</span> <span class="metricunit" data-ui="' + key + '-unit"></span></div></div>'
      ).join('') + '</div>' +
      '<div class="adjustments"><div class="block"><div class="line"><span class="label">Целевая влажность</span><span class="target" data-ui="target">—</span></div>' +
      '<input type="range" min="30" max="70" step="1" data-action="target" aria-label="Целевая влажность" disabled><div class="range"><span>30%</span><span>70%</span></div></div>' +
      '<div class="block"><span class="label">Скорость вентилятора</span><div class="buttons five">' +
      [1,2,3,4,5].map(n => '<button type="button" class="seg" data-fan="'+n+'" aria-label="Скорость '+n+'" aria-pressed="false" disabled>'+n+'</button>').join('') +
      '</div></div></div>' +
      '<div class="block"><span class="label">Режим</span><div class="buttons">' +
      [['Auto','Авто'],['Manual','Ручной'],['Sleep','Ночной']].map(([v,l]) => '<button type="button" class="seg" data-mode="'+v+'" aria-pressed="false" disabled>'+l+'</button>').join('') +
      '</div></div>' +
      '<div class="block"><div class="line"><span class="label">LED-подсветка</span><button type="button" class="seg" data-action="led" aria-label="Подсветка" aria-pressed="false" disabled>LED</button></div>' +
      '<div class="colors">' + colors.map(([v,c]) => '<button type="button" class="colorbtn" data-color="'+v+'" aria-label="Цвет '+v+'" aria-pressed="false" title="'+v+'" disabled><span style="background:'+c+'"></span></button>').join('') + '</div>' +
      '<label>Яркость <b data-ui="brightness">—</b><input type="range" min="1" max="8" step="1" data-action="brightness" aria-label="Яркость подсветки" disabled></label></div>' +
      '<div class="msg" data-ui="message" role="status" aria-live="polite"></div></ha-card>';

    this.shadowRoot.addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b || b.disabled || !this._config) return;
      const c = this._config;
      if (b.dataset.action === "power") this._call("humidifier", this._value(c.entity) === "on" ? "turn_off" : "turn_on", {entity_id:c.entity});
      else if (b.dataset.action === "led") this._call("switch", this._value(c.led) === "on" ? "turn_off" : "turn_on", {entity_id:c.led});
      else if (b.dataset.mode) this._call("humidifier","set_mode",{entity_id:c.entity,mode:b.dataset.mode});
      else if (b.dataset.fan) this._call("select","select_option",{entity_id:c.fan,option:b.dataset.fan});
      else if (b.dataset.color) this._call("select","select_option",{entity_id:c.color,option:b.dataset.color});
    });
    for (const action of ["target","brightness"]) {
      const slider = this.shadowRoot.querySelector('[data-action="'+action+'"]');
      slider.addEventListener("input", e => {
        if (!slider.disabled) this._node(action).textContent = e.target.value + (action === "target" ? "%" : "");
      });
      slider.addEventListener("change", e => {
        if (slider.disabled) { this._sync(true); return; }
        const c = this._config;
        if (action === "target") this._call("humidifier","set_humidity",{entity_id:c.entity,humidity:Number(e.target.value)});
        else this._call("select","select_option",{entity_id:c.brightness,option:e.target.value});
      });
    }
  }

  async _call(domain, service, data) {
    if (!this._allowed(domain, service, data)) { this._sync(true); return; }
    this._sending = true;
    const msg = this._node("message");
    msg.classList.remove("error");
    msg.textContent = "Применение…";
    this._sync();
    try {
      await this._hass.callService(domain, service, data);
      msg.textContent = "Команда отправлена. Состояние обновится из HA.";
    } catch {
      // Do not echo arbitrary backend messages, which may contain private details.
      msg.textContent = "Команда не выполнена. Проверьте связь и права.";
      msg.classList.add("error");
    } finally {
      this._sending = false;
      this._sync(true);
    }
  }

  _sync(force = false) {
    if (!this._mounted || !this._config) return;
    const c = this._config, h = this._entity(c.entity);
    const available = ["on","off"].includes(this._value(c.entity)), on = this._value(c.entity) === "on";
    this._node("status").textContent = !available ? "Нет связи" : on ? "Работает" : "Выключена";
    this._node("pm25-tile").hidden = !c.pm25;
    this._node("water-tile").hidden = !c.water;
    for (const key of ["humidity","temperature","pm25","water"]) {
      const state = this._entity(c[key]);
      let value = this._value(c[key]), unit = state?.attributes?.unit_of_measurement || "";
      if (key === "humidity" && value === null && !state && available) {
        value = h?.attributes?.current_humidity ?? null; unit = "%";
      }
      this._node(key).textContent = value ?? "—";
      this._node(key+"-unit").textContent = value == null ? "" : unit;
    }
    const button = (selector, active, domain, service, data) => {
      const b = this.shadowRoot.querySelector(selector);
      b.setAttribute("aria-pressed", String(active));
      b.disabled = !this._allowed(domain,service,data);
    };
    button('[data-action="power"]',on,"humidifier",on?"turn_off":"turn_on",{entity_id:c.entity});
    const ledOn = this._value(c.led) === "on";
    button('[data-action="led"]',ledOn,"switch",ledOn?"turn_off":"turn_on",{entity_id:c.led});
    this.shadowRoot.querySelectorAll("[data-mode]").forEach(b => {
      b.setAttribute("aria-pressed", String(b.dataset.mode === h?.attributes?.mode && available));
      b.disabled = !this._allowed("humidifier","set_mode",{entity_id:c.entity,mode:b.dataset.mode});
    });
    for (const [selector,key,attribute] of [["[data-fan]","fan","fan"],["[data-color]","color","color"]]) {
      this.shadowRoot.querySelectorAll(selector).forEach(b => {
        const v = b.dataset[attribute];
        b.setAttribute("aria-pressed", String(v === this._value(c[key])));
        b.disabled = !this._allowed("select","select_option",{entity_id:c[key],option:v});
      });
    }
    const slider = this.shadowRoot.querySelector('[data-action="target"]');
    const target = h?.attributes?.humidity;
    slider.disabled = !available || target == null || !this._allowed("humidifier","set_humidity",{entity_id:c.entity,humidity:Number(target)});
    if (force || this.shadowRoot.activeElement !== slider || slider.disabled) {
      const t = Number(target);
      const valid = available && target != null && Number.isInteger(t) && t >= 30 && t <= 70;
      if (valid) slider.value = String(t);
      this._node("target").textContent = valid ? t+"%" : "—";
    }
    const brightness = this.shadowRoot.querySelector('[data-action="brightness"]');
    const bv = this._value(c.brightness);
    const validBrightness = bv != null && /^[1-8]$/.test(bv);
    brightness.disabled = !validBrightness || !this._allowed("select","select_option",{entity_id:c.brightness,option:bv});
    if (force || this.shadowRoot.activeElement !== brightness || brightness.disabled) {
      if (validBrightness) brightness.value = bv;
      this._node("brightness").textContent = validBrightness ? bv : "—";
    }
  }
}

if (!customElements.get("venta-airwasher-card")) customElements.define("venta-airwasher-card", VentaAirwasherCard);
window.customCards = window.customCards || [];
if (!window.customCards.some(x => x.type === "venta-airwasher-card")) {
  window.customCards.push({type:"venta-airwasher-card",name:"Venta AW730",description:"Управление мойкой воздуха в одной карточке"});
}
