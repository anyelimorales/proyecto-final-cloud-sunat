"use strict";
// Portal de trámites. Todo el contenido dinámico se inserta con textContent (sin innerHTML) para evitar XSS.
const $ = (s) => document.querySelector(s);
const estado = { token: sessionStorage.getItem("token"), ruc: sessionStorage.getItem("ruc"), vista: "inicio" };
const soles = (n) => "S/ " + Number(n).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---- Textos legibles ------------------------------------------------------------------------
// La API devuelve identificadores internos (minúsculas, sin tildes, con guiones bajos). Nunca se muestran
// tal cual: se traducen a la ortografía normal del español (mayúscula inicial, tildes y siglas correctas).
const cap = (t) => { const s = String(t ?? ""); return s.charAt(0).toUpperCase() + s.slice(1); };
const ETIQUETA_ESTADO = { urgente: "Urgente", proximo: "Próximo", vencido: "Vencido", programado: "Programado" };
const ETIQUETA_ORIGEN = { constancia: "Constancia", sustento: "Sustento" };
const ETIQUETA_TRAMITE = { rhe: "Recibo por honorarios", declaracion: "Declaración anual", pago_a_cuenta: "Pago a cuenta",
  fraccionamiento: "Fraccionamiento", tramite_ruc: "Trámite RUC", otro: "Otro" };
const SUBSANACIONES = [{ valor: "voluntaria_antes_de_notificacion", texto: "Voluntaria antes de notificación" },
  { valor: "inducida_dentro_del_plazo", texto: "Inducida dentro del plazo" }, { valor: "ninguna", texto: "Ninguna" }];
const CANALES = [{ valor: "correo", texto: "Correo" }, { valor: "sms", texto: "SMS" }, { valor: "whatsapp", texto: "WhatsApp" }];
const etiquetaEstado = (e) => ETIQUETA_ESTADO[e] || cap(e);
const etiquetaTramite = (t) => ETIQUETA_TRAMITE[t] || cap(String(t ?? "").replaceAll("_", " "));

function h(tag, attrs, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null) continue;
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const c of hijos.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}

// ---- Iconos SVG en línea (trazos estilo Lucide; createElementNS, sin archivos ni CDN) ----------
const SVG_NS = "http://www.w3.org/2000/svg";
const ICONOS = {
  calendario: ["M8 2v4", "M16 2v4", "M3 10h18", "M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"],
  simulador: ["M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z", "M9 6h6", "M9 11h.01", "M12 11h.01", "M15 11h.01", "M9 15h.01", "M12 15h.01", "M15 15h.01", "M9 19h6"],
  fracc: ["M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z", "M2 10h20", "M6 14h4"],
  ficha: ["M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M9.5 13a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4z", "M6 17a3.8 3.8 0 0 1 7 0", "M16 9.5h3", "M16 13.5h3"],
  rhe: ["M6 2h12a1 1 0 0 1 1 1v18l-3-2-3 2-3-2-3 2V3a1 1 0 0 1 1-1z", "M9 7h6", "M9 11h6", "M9 15h3"],
  declaracion: ["M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z", "M14 2v5h5", "M9 13h6", "M9 17h4"],
  alertas: ["M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6z", "M10.4 20a1.9 1.9 0 0 0 3.2 0"],
  inicio: ["m3 10 9-7 9 7v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M9 21v-7h6v7"],
  pagos: ["M12 2v20", "M17 6.5A3.5 3.5 0 0 0 13.5 4h-3a3.5 3.5 0 0 0 0 7h3a3.5 3.5 0 0 1 0 7h-3.5A3.5 3.5 0 0 1 6.5 15"],
  flecha: ["M5 12h14", "m13 6 6 6-6 6"],
  expediente: ["M4 4h5l2 3h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M8 14h8"],
  descargar: ["M12 3v12", "m7 11 5 5 5-5", "M5 21h14"],
  menu: ["M4 7h16", "M4 12h16", "M4 17h16"],
  cerrar: ["m6 6 12 12", "m18 6-12 12"],
  entrar: ["M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4", "m10 17 5-5-5-5", "M15 12H3"],
  salir: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "m16 17 5-5-5-5", "M21 12H9"],
};

function icono(nombre, tam = 19) {
  const s = document.createElementNS(SVG_NS, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: tam, height: tam, fill: "none", stroke: "currentColor",
    "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "ic" })) s.setAttribute(k, v);
  for (const d of ICONOS[nombre] || []) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d);
    s.append(p);
  }
  return s;
}

async function api(ruta, { metodo = "GET", cuerpo, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && estado.token) headers.Authorization = "Bearer " + estado.token;
  const r = await fetch(ruta, { method: metodo, headers, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
  const dato = await r.json().catch(() => ({}));
  if (r.status === 401 && auth) { cerrarSesion(); throw new Error("Su sesión expiró. Ingrese nuevamente."); }
  if (!r.ok) throw new Error(typeof dato.detail === "string" ? dato.detail : dato.detail ? "Revise los datos ingresados." : "Error " + r.status);
  return dato;
}

const aviso = (tipo, texto) => h("div", { class: "msg " + tipo, role: tipo === "error" ? "alert" : "status" }, texto);

function formulario(campos, textoBoton, alEnviar, salida) {
  const f = h("form", {});
  for (const c of campos) {
    const id = "f_" + c.n;
    const ctl = c.opciones
      ? h("select", { id, name: c.n }, c.opciones.map((o) => typeof o === "string" ? h("option", { value: o }, o) : h("option", { value: o.valor }, o.texto)))
      : h("input", { id, name: c.n, type: c.t || "text", value: c.v ?? "", required: c.req === false ? null : "", step: c.t === "number" ? "any" : null, min: c.min ?? null, max: c.max ?? null, autocomplete: c.ac || "off", inputmode: c.im || null, pattern: c.p || null });
    if (c.req === false) ctl.removeAttribute("required");
    f.append(h("label", { for: id }, c.l), ctl);
  }
  f.append(h("div", { class: "acciones" }, h("button", { type: "submit" }, textoBoton)));
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    salida.replaceChildren();
    const datos = {};
    for (const c of campos) { const v = f.elements[c.n].value; datos[c.n] = c.t === "number" ? Number(v || 0) : v; }
    try { await alEnviar(datos, salida); } catch (e) { salida.replaceChildren(aviso("error", e.message)); }
  });
  return f;
}

function tabla(cabeceras, filas) {
  return h("div", { class: "tabla" }, h("table", {}, h("thead", {}, h("tr", {}, cabeceras.map((c) => h("th", {}, c)))),
    h("tbody", {}, filas.map((f) => h("tr", {}, f.map((c) => h("td", {}, c)))))));
}
const kv = (pares) => h("div", { class: "kv" }, pares.flatMap(([k, v]) => [h("span", {}, k), h("b", {}, v)]));

// ---- Componentes del tablero -------------------------------------------------
function hero() {
  const con = Boolean(estado.token);
  return h("div", { class: "hero" },
    h("div", { class: "hero-txt" },
      h("h2", {}, con ? "Hola de nuevo" : "Portal de trámites tributarios"),
      h("p", {}, con ? "RUC " + estado.ruc + " · todos sus trámites en un solo lugar"
                     : "Consulte vencimientos, simule multas y fraccionamientos sin iniciar sesión.")),
    h("div", { class: "hero-acc" }, con
      ? [h("button", { type: "button", class: "hero-btn", onclick: () => irA("rhe") }, "Emitir recibo"),
         h("button", { type: "button", class: "hero-btn hueco", onclick: () => irA("alertas") }, "Ver vencimientos")]
      : h("button", { type: "button", class: "hero-btn", onclick: () => irA("login") }, "Ingresar")));
}

const MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

// Tira horizontal con los próximos vencimientos (día grande + mes), al estilo de una agenda.
function tiraVencimientos(items) {
  if (!items.length) return null;
  return h("div", { class: "tira", role: "list", "aria-label": "Próximos vencimientos" },
    items.slice(0, 7).map((v) => {
      const f = v.vence.split("-");
      return h("button", { type: "button", role: "listitem", class: "tira-dia est-" + v.estado,
        "aria-label": `${v.obligacion}, vence el ${v.vence}, ${etiquetaEstado(v.estado).toLowerCase()}`,
        onclick: () => irA(estado.token ? "alertas" : "calendario") },
        h("span", { class: "tira-num" }, String(Number(f[2]))),
        h("span", { class: "tira-mes" }, MES_CORTO[Number(f[1]) - 1]),
        h("span", { class: "tira-pt" }));
    }));
}

// Barra de proporción (dos partes de un total): un solo tono en dos pasos + etiquetas directas.
function barraProporcion(partes, total) {
  if (!total) return null;
  return h("div", { class: "prop" },
    h("div", { class: "prop-barra" }, partes.map((p) =>
      h("span", { class: "prop-seg " + p.clase, style: null, "data-w": String(p.valor / total * 100) }))),
    h("ul", { class: "prop-leyenda" }, partes.map((p) =>
      h("li", {}, h("span", { class: "prop-punto " + p.clase }), h("span", {}, p.etiqueta),
        h("b", {}, soles(p.valor) + " · " + (p.valor / total * 100).toFixed(1) + " %")))));
}

// Barras horizontales por mes (una sola serie: sin leyenda, con el valor como etiqueta directa).
function barrasPorMes(filas) {
  const max = Math.max(...filas.map((f) => f.valor));
  return h("div", { class: "barras" }, filas.map((f) =>
    h("div", { class: "barra-fila", title: `${cap(f.etiqueta)}: ${soles(f.valor)} en ${f.n} recibo(s)` },
      h("span", { class: "barra-et" }, f.etiqueta),
      h("span", { class: "barra-via" }, h("span", { class: "barra-relleno", "data-w": String(f.valor / max * 100) })),
      h("b", { class: "barra-val" }, soles(f.valor)))));
}

// Las anchuras se aplican por JS (data-w) para no usar atributos style en línea (CSP).
function aplicarAnchos(raiz) {
  for (const e of raiz.querySelectorAll("[data-w]")) e.style.width = e.dataset.w + "%";
}

function tarjetaTramite(clave, descripcion, tono) {
  return h("button", { type: "button", class: "tramite tono-" + tono, onclick: () => irA(clave) },
    h("span", { class: "tramite-ic" }, icono(clave, 24)),
    h("span", { class: "tramite-txt" }, h("strong", {}, vistas[clave].titulo), h("span", {}, descripcion)),
    h("span", { class: "flecha" }, icono("flecha", 18)));
}

function indicador(destino, etiqueta, valor, sub, pct, tono) {
  return h("button", { type: "button", class: "tile tono-" + tono, onclick: () => irA(destino) },
    h("span", { class: "tile-cab" }, h("span", { class: "tile-ic" }, icono(destino, 20)),
      h("span", { class: "tile-ir" }, icono("flecha", 15))),
    h("span", { class: "tile-val" }, String(valor)),
    h("span", { class: "tile-lab" }, etiqueta),
    pct == null ? null : h("span", { class: "tile-bar" }, h("i", { "data-w": String(Math.min(pct, 100)) })),
    sub ? h("span", { class: "tile-sub" }, sub) : null);
}

function indicadores() {
  const cont = h("div", { class: "tiles" });
  Promise.all([
    api("/api/rhe", { auth: true }).catch(() => []),
    api("/api/declaraciones", { auth: true }).catch(() => []),
    api("/api/alertas/mis-vencimientos", { auth: true }).catch(() => ({ vencimientos: [] })),
  ]).then(([rs, ds, mv]) => {
    const vencs = mv.vencimientos || [];
    const porAtender = vencs.filter((v) => v.estado === "urgente" || v.estado === "vencido").length;
    const emitidos = rs.filter((r) => r.estado === "emitido").length;
    const originales = ds.filter((d) => d.tipo === "original").length;
    cont.replaceChildren(
      indicador("rhe", "Recibos emitidos", emitidos,
        rs.length ? `${rs.length - emitidos} anulado(s) de ${rs.length}` : "Aún no emite recibos",
        rs.length ? emitidos / rs.length * 100 : 0, "azul"),
      indicador("declaracion", "Declaraciones presentadas", ds.length,
        ds.length ? `${originales} original(es) · ${ds.length - originales} rectificatoria(s)` : "Sin declaraciones",
        ds.length ? originales / ds.length * 100 : 0, "azul"),
      indicador("alertas", "Vencimientos por atender", porAtender,
        vencs.length ? `de ${vencs.length} en seguimiento` : "Sin vencimientos cercanos",
        vencs.length ? porAtender / vencs.length * 100 : 0, porAtender ? "rojo" : "azul"));
    aplicarAnchos(cont);
  }).catch(() => cont.remove());
  return cont;
}

// Tabla de vencimientos con filtros por estado (se filtra en el cliente, sin volver a consultar)
function tablaVencimientos(items) {
  const cuerpo = h("div", {});
  const estados = [["todos", "Todos"], ["urgente", "Urgentes"], ["proximo", "Próximos"], ["vencido", "Vencidos"]];
  let activo = "todos";
  const repintar = () => {
    const vis = activo === "todos" ? items : items.filter((v) => v.estado === activo);
    cuerpo.replaceChildren(vis.length
      ? tabla(["Obligación", "Período", "Vence", "Días", "Estado"], vis.map((v) =>
          [v.obligacion, v.periodo, v.vence, v.dias_restantes, h("span", { class: "chip " + v.estado }, etiquetaEstado(v.estado))]))
      : aviso("info", "No hay vencimientos con ese estado."));
  };
  const barra = h("div", { class: "filtros", role: "group", "aria-label": "Filtrar vencimientos por estado" },
    estados.map(([clave, texto]) => h("button", { type: "button", class: "filtro", "aria-pressed": String(clave === activo),
      onclick: (ev) => {
        activo = clave;
        for (const b of barra.querySelectorAll(".filtro")) b.setAttribute("aria-pressed", String(b === ev.currentTarget));
        repintar();
      } }, texto)));
  repintar();
  return h("div", {}, barra, cuerpo);
}

// ---- Vistas --------------------------------------------------------------
const vistas = {
  inicio: { titulo: "Inicio", sub: "Sus trámites tributarios en un solo lugar", publica: true, panel: true, render(raiz) {
    raiz.append(hero());
    if (estado.token) raiz.append(indicadores());
    const digito = estado.ruc ? Number(estado.ruc.slice(-1)) : estado.digito;
    if (digito != null && Number.isFinite(digito)) {
      const franja = h("div", {});
      raiz.append(franja);
      api(`/api/alertas/calendario/${digito}`).then((r) => {
        const prox = r.vencimientos.filter((v) => v.dias_restantes >= 0);
        const tira = tiraVencimientos(prox);
        if (tira) franja.replaceChildren(h("h2", { class: "sec-tit" }, "Próximos vencimientos"), tira);
      }).catch(() => franja.remove());
    }
    const fichas = [
      ["calendario", "Consulte cuándo vencen sus obligaciones según el último dígito de su RUC."],
      ["simulador", "Estime multas e intereses y vea cuánto ahorra si subsana de forma voluntaria."],
      ["fracc", "Simule el pago de una deuda en cuotas y revise el cronograma completo."],
      ["ficha", "Consulte y actualice su domicilio, actividad económica y régimen tributario."],
      ["rhe", "Emita recibos por honorarios, calcule la retención y anule los que necesite."],
      ["pagos", "Determine su pago a cuenta mensual a partir de los recibos del periodo y preséntelo."],
      ["declaracion", "Calcule su declaración anual de renta y preséntela o rectifíquela."],
      ["expediente", "Descargue las constancias de sus trámites y adjunte los sustentos que necesite."],
      ["alertas", "Revise sus próximos vencimientos y suscríbase a avisos por correo o SMS."],
    ].filter(([k]) => vistas[k].publica || estado.token);
    raiz.append(h("div", { class: "tramites" }, fichas.map(([k, d], i) => tarjetaTramite(k, d, i % 3))));
  } },
  calendario: { titulo: "Calendario", sub: "Vencimientos del año según el último dígito del RUC", publica: true, panel: true, render(raiz) {
    const salida = h("div", {});
    const digito = estado.ruc ? estado.ruc.slice(-1) : "0";
    raiz.append(h("div", { class: "card" }, h("h2", {}, "Calendario de vencimientos"),
      h("p", {}, "Los vencimientos dependen del último dígito de su RUC. Información pública."),
      formulario([{ n: "digito", l: "Último dígito del RUC", t: "number", min: 0, max: 9, v: digito }], "Consultar", async (d, out) => {
        const r = await api(`/api/alertas/calendario/${Number(d.digito)}`);
        estado.digito = Number(d.digito);          // alimenta el panel lateral
        pintarPanel();
        out.append(tablaVencimientos(r.vencimientos));
      }, salida)), salida);
  } },
  simulador: { titulo: "Simulador de multas", sub: "Estime multas, intereses y el ahorro por subsanar a tiempo", publica: true, render(raiz) {
    const salida = h("div", {});
    raiz.append(h("div", { class: "card" }, h("h2", {}, "Simulador de multas e intereses"),
      h("p", {}, "Estime el costo de un incumplimiento y el ahorro de subsanar de forma voluntaria."),
      formulario([
        { n: "tributo_omitido", l: "Tributo omitido o pendiente (S/)", t: "number", v: 1000, min: 0 },
        { n: "dias_retraso", l: "Días de retraso", t: "number", v: 30, min: 0, max: 3650 },
        { n: "subsanacion", l: "Subsanación", opciones: SUBSANACIONES },
      ], "Simular", async (d, out) => {
        const r = await api("/api/simulador/multa", { metodo: "POST", cuerpo: d });
        out.append(kv([["Multa sin rebaja", soles(r.multa_sin_rebaja)], ["Multa con rebaja", soles(r.multa_con_rebaja)],
          ["Interés sobre el tributo", soles(r.interes_sobre_tributo)], ["Interés sobre la multa", soles(r.interes_sobre_multa)],
          ["Total estimado", soles(r.total_estimado)], ["Ahorro por subsanar ahora", soles(r.ahorro_por_subsanar_ahora)]]));
      }, salida)), salida);
  } },
  fracc: { titulo: "Fraccionamiento", sub: "Simule el pago de una deuda en cuotas mensuales", publica: true, render(raiz) {
    const salida = h("div", {});
    const campos = [{ n: "deuda", l: "Deuda (S/)", t: "number", v: 6000, min: 1 }, { n: "cuotas", l: "Número de cuotas (2 a 72)", t: "number", v: 12, min: 2, max: 72 }];
    const card = h("div", { class: "card" }, h("h2", {}, "Aplazamiento y fraccionamiento"),
      formulario(campos, "Simular", async (d, out) => {
        const r = await api("/api/fraccionamiento/simular", { metodo: "POST", cuerpo: d });
        out.append(kv([["Cuota mensual", soles(r.cuota_mensual)], ["Total a pagar", soles(r.total_a_pagar)], ["Intereses", soles(r.total_intereses)]]),
          tabla(["N.º", "Cuota", "Interés", "Amortización", "Saldo"], r.cronograma.map((c) => [c.n, soles(c.cuota), soles(c.interes), soles(c.amortizacion), soles(c.saldo)])));
        if (estado.token) out.append(h("div", { class: "acciones" }, h("button", { type: "button", onclick: async () => {
          try { const s = await api("/api/fraccionamiento/solicitar", { metodo: "POST", cuerpo: d, auth: true }); out.prepend(aviso("ok", `Solicitud registrada (${s.estado}).`)); } catch (e) { out.prepend(aviso("error", e.message)); }
        } }, "Solicitar este fraccionamiento")));
        else out.append(aviso("info", "Inicie sesión para solicitar el fraccionamiento."));
      }, salida));
    raiz.append(card, salida);
  } },
  ficha: { titulo: "Mi ficha RUC", sub: "Consulte y actualice sus datos de contribuyente", render(raiz) {
    const salida = h("div", {});
    const info = h("div", { class: "card" }, h("h2", {}, "Ficha RUC"), "Cargando…");
    raiz.append(info, salida);
    api("/api/ruc/ficha", { auth: true }).then(async (f) => {
      const regs = await api("/api/ruc/regimenes");
      info.replaceChildren(h("h2", {}, "Ficha RUC"), kv([["RUC", f.ruc], ["Nombre", f.razon_social], ["Domicilio", f.domicilio], ["Actividad", f.actividad], ["Régimen", f.regimen]]),
        h("h2", { class: "sep" }, "Actualizar datos"),
        formulario([{ n: "domicilio", l: "Domicilio", v: f.domicilio }, { n: "actividad", l: "Actividad económica", v: f.actividad }], "Guardar", async (d, out) => {
          await api("/api/ruc/ficha", { metodo: "PUT", cuerpo: d, auth: true }); out.append(aviso("ok", "Datos actualizados."));
        }, salida),
        h("h2", { class: "sep" }, "Cambio de régimen"),
        formulario([{ n: "regimen", l: "Nuevo régimen", opciones: regs }], "Solicitar cambio", async (d, out) => {
          await api("/api/ruc/cambio-regimen", { metodo: "POST", cuerpo: d, auth: true }); out.append(aviso("ok", "Cambio de régimen registrado."));
        }, salida));
    }).catch((e) => info.append(aviso("error", e.message)));
  } },
  rhe: { titulo: "Recibos por honorarios", sub: "Emita, consulte y anule sus recibos electrónicos", render(raiz) {
    const salida = h("div", {}), lista = h("div", { class: "card" }), resumen = h("div", {});
    const pintarResumen = (rs) => {
      const anio = new Date().getFullYear();
      const vigentes = rs.filter((r) => r.estado === "emitido" && r.fecha.startsWith(String(anio)));
      if (!vigentes.length) { resumen.replaceChildren(); return; }
      const bruto = vigentes.reduce((a, r) => a + r.monto_bruto, 0);
      const ret = vigentes.reduce((a, r) => a + r.retencion, 0);
      const porMes = new Map();
      for (const r of vigentes) {
        const m = Number(r.fecha.slice(5, 7)) - 1;
        const acc = porMes.get(m) || { valor: 0, n: 0 };
        porMes.set(m, { valor: acc.valor + r.monto_bruto, n: acc.n + 1 });
      }
      const filas = [...porMes.entries()].sort((a, b) => a[0] - b[0])
        .map(([m, v]) => ({ etiqueta: MES_CORTO[m], valor: v.valor, n: v.n }));
      const card = h("div", { class: "card" },
        h("h2", {}, `Resumen ${anio}`),
        h("div", { class: "cifras" },
          h("div", {}, h("span", {}, "Total bruto"), h("b", {}, soles(bruto))),
          h("div", {}, h("span", {}, "Retención"), h("b", {}, soles(ret))),
          h("div", {}, h("span", {}, "Neto recibido"), h("b", {}, soles(bruto - ret)))),
        barraProporcion([
          { etiqueta: "Neto recibido", valor: bruto - ret, clase: "p-neto" },
          { etiqueta: "Retención de cuarta", valor: ret, clase: "p-ret" }], bruto),
        h("h2", { class: "sep" }, "Monto bruto por mes"),
        h("p", { class: "nota-graf" }, "El detalle de cada recibo está en la tabla de abajo."),
        barrasPorMes(filas));
      resumen.replaceChildren(card);
      aplicarAnchos(card);
    };
    const cargar = async () => {
      const rs = await api("/api/rhe", { auth: true });
      pintarResumen(rs);
      lista.replaceChildren(h("h2", {}, "Mis recibos"), rs.length ? tabla(["N.º", "Fecha", "Cliente", "Bruto", "Retención", "Neto", "Estado", ""],
        rs.map((r) => [r.numero, r.fecha, r.cliente_nombre, soles(r.monto_bruto), soles(r.retencion), soles(r.monto_neto), cap(r.estado),
          r.estado === "emitido" ? h("button", { type: "button", class: "critico", onclick: async () => { const m = prompt("Motivo de la anulación (mín. 5 caracteres):"); if (m) { try { await api(`/api/rhe/${r.id}/anular`, { metodo: "POST", cuerpo: { motivo: m }, auth: true }); cargar(); } catch (e) { salida.replaceChildren(aviso("error", e.message)); } } } }, "Anular") : ""])) : "Aún no ha emitido recibos.");
    };
    raiz.append(h("div", { class: "card" }, h("h2", {}, "Emitir recibo por honorarios"), formulario([
      { n: "cliente_ruc", l: "RUC del cliente", im: "numeric", p: "\\d{11}" }, { n: "cliente_nombre", l: "Nombre o razón social del cliente" },
      { n: "descripcion", l: "Descripción del servicio" }, { n: "monto_bruto", l: "Monto bruto (S/)", t: "number", min: 0.01 }], "Emitir", async (d, out) => {
      const r = await api("/api/rhe", { metodo: "POST", cuerpo: d, auth: true });
      out.append(aviso("ok", `Recibo ${r.numero} emitido. Retención: ${soles(r.retencion)}. Neto: ${soles(r.monto_neto)}.`)); cargar();
    }, salida)), salida, resumen, lista);
    cargar().catch((e) => lista.append(aviso("error", e.message)));
  } },
  declaracion: { titulo: "Declaración anual", sub: "Calcule y presente su declaración de renta de cuarta y quinta", render(raiz) {
    const salida = h("div", {}), hist = h("div", { class: "card" });
    const campos = [{ n: "ejercicio", l: "Ejercicio", t: "number", v: new Date().getFullYear() - 1 }, { n: "ingresos_cuarta", l: "Ingresos de cuarta categoría (S/)", t: "number", v: 0, min: 0 },
      { n: "ingresos_quinta", l: "Ingresos de quinta categoría (S/)", t: "number", v: 0, min: 0 }, { n: "gastos_deducibles", l: "Gastos deducibles ya reducidos a su porcentaje (S/)", t: "number", v: 0, min: 0 },
      { n: "retenciones", l: "Retenciones sufridas (S/)", t: "number", v: 0, min: 0 }, { n: "pagos_a_cuenta", l: "Pagos a cuenta efectuados (S/)", t: "number", v: 0, min: 0 }, { n: "saldo_favor_anterior", l: "Saldo a favor anterior (S/)", t: "number", v: 0, min: 0 }];
    const mostrar = (r, out) => out.append(kv([["Deducción 20 % (cuarta)", soles(r.deduccion_20pct_cuarta)], ["Deducción 7 UIT", soles(r.deduccion_7_uit)], ["Base imponible", soles(r.base_imponible)],
      ["Impuesto determinado", soles(r.impuesto_determinado)], ["Créditos aplicados", soles(r.creditos_aplicados)], ["Saldo a pagar", soles(r.saldo_a_pagar)], ["Saldo a favor", soles(r.saldo_a_favor)]]));
    const f = formulario(campos, "Calcular", async (d, out) => {
      mostrar(await api("/api/declaraciones/calcular", { metodo: "POST", cuerpo: d, auth: true }), out);
      out.append(h("div", { class: "acciones" },
        h("button", { type: "button", onclick: async () => { try { const r = await api("/api/declaraciones", { metodo: "POST", cuerpo: d, auth: true }); out.prepend(aviso("ok", "Declaración presentada. N.º de orden " + r.numero_orden)); cargarHist(); } catch (e) { out.prepend(aviso("error", e.message)); } } }, "Presentar declaración"),
        h("button", { type: "button", class: "sec", onclick: async () => { try { const r = await api("/api/declaraciones/rectificar", { metodo: "POST", cuerpo: d, auth: true }); out.prepend(aviso("ok", "Rectificatoria presentada. N.º de orden " + r.numero_orden)); cargarHist(); } catch (e) { out.prepend(aviso("error", e.message)); } } }, "Presentar rectificatoria")));
    }, salida);
    const cargarHist = async () => {
      const ds = await api("/api/declaraciones", { auth: true });
      hist.replaceChildren(h("h2", {}, "Declaraciones presentadas"), ds.length ? tabla(["Ejercicio", "Tipo", "Versión", "Presentada", "Saldo a pagar", "Saldo a favor"],
        ds.map((d) => [d.ejercicio, cap(d.tipo), d.version, d.presentada, soles(d.resultado.saldo_a_pagar), soles(d.resultado.saldo_a_favor)])) : "Sin declaraciones.");
    };
    raiz.append(h("div", { class: "card" }, h("h2", {}, "Declaración anual de renta"), f), salida, hist);
    cargarHist().catch((e) => hist.append(aviso("error", e.message)));
  } },
  pagos: { titulo: "Pagos a cuenta", sub: "Determine y presente su pago a cuenta mensual de cuarta categoría", render(raiz) {
    const salida = h("div", {}), hist = h("div", { class: "card" });
    const hoy = new Date();
    const mesActual = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
    const mostrar = (r, out) => {
      if (!r.obligado) out.append(aviso("ok", r.motivo_exoneracion));
      out.append(
        kv([["Recibos del periodo", String(r.recibos_considerados)], ["Ingresos del periodo", soles(r.ingresos_del_periodo)],
            ["Pago a cuenta (8 %)", soles(r.pago_a_cuenta_bruto)], ["Retenciones ya efectuadas", soles(r.retenciones_del_periodo)],
            ["Importe a pagar", soles(r.importe_a_pagar)]]));
      out.append(h("div", { class: "acciones" }, h("button", { type: "button", onclick: async () => {
        try {
          const p = await api("/api/pagos", { metodo: "POST", cuerpo: { periodo: r.periodo }, auth: true });
          out.prepend(aviso("ok", "Pago a cuenta presentado. N.º de orden " + p.numero_orden));
          cargarHist();
        } catch (e) { out.prepend(aviso("error", e.message)); }
      } }, "Presentar pago a cuenta")));
    };
    const cargarHist = async () => {
      const ps = await api("/api/pagos", { auth: true });
      hist.replaceChildren(h("h2", {}, "Pagos a cuenta presentados"), ps.length
        ? tabla(["Periodo", "Ingresos", "Retenciones", "Importe", "Presentado", "Estado"],
            ps.map((p) => [p.periodo, soles(p.ingresos_del_periodo), soles(p.retenciones_del_periodo),
                           soles(p.importe_a_pagar), p.presentado, cap(p.estado)]))
        : "Aún no ha presentado pagos a cuenta.");
    };
    raiz.append(h("div", { class: "card" }, h("h2", {}, "Determinación del periodo"),
      h("p", {}, "El importe se calcula con los recibos por honorarios que usted ya emitió en el mes."),
      formulario([{ n: "periodo", l: "Periodo (AAAA-MM)", v: mesActual, p: "\\d{4}-(0[1-9]|1[0-2])" }], "Calcular", async (d, out) => {
        mostrar(await api(`/api/pagos/periodo/${d.periodo}`, { auth: true }), out);
      }, salida)), salida, hist);
    cargarHist().catch((e) => hist.append(aviso("error", e.message)));
  } },
  expediente: { titulo: "Mi expediente", sub: "Constancias de sus trámites y sustentos adjuntos", render(raiz) {
    const salida = h("div", {}), lista = h("div", { class: "card" });
    const cargar = async () => {
      const docs = await api("/api/documentos", { auth: true });
      lista.replaceChildren(h("h2", {}, "Documentos archivados"), docs.length
        ? tabla(["Documento", "Trámite", "Referencia", "Origen", "Archivado", ""], docs.map((d) => [
            d.titulo, etiquetaTramite(d.tramite), d.referencia || "—",
            h("span", { class: "chip " + (d.origen === "constancia" ? "programado" : "proximo") }, ETIQUETA_ORIGEN[d.origen] || cap(d.origen)),
            d.archivado.slice(0, 10),
            h("button", { type: "button", class: "sec", onclick: () => descargar(d) }, "Descargar"),
          ]))
        : "Aún no hay documentos en su expediente. Se archivan solos al completar un trámite.");
    };
    // La descarga pasa por fetch para poder enviar el token; el archivo nunca sale en la URL.
    const descargar = async (d) => {
      try {
        const r = await fetch(`/api/documentos/${d.id}`, { headers: { Authorization: "Bearer " + estado.token } });
        if (!r.ok) throw new Error("No se pudo descargar el documento");
        const url = URL.createObjectURL(await r.blob());
        const a = h("a", { href: url, download: d.nombre_archivo });
        document.body.append(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) { salida.prepend(aviso("error", e.message)); }
    };
    raiz.append(h("div", { class: "card" }, h("h2", {}, "Adjuntar un sustento"),
      h("p", {}, "Archivos PDF, PNG o JPG de hasta 2 MB."),
      (() => {
        const f = h("form", { class: "form" });
        const campos = h("div", {},
          h("label", { for: "f_titulo" }, "Título del documento"),
          h("input", { id: "f_titulo", required: "", maxlength: "120" }),
          h("label", { for: "f_tramite" }, "Trámite"),
          h("select", { id: "f_tramite" }, Object.entries(ETIQUETA_TRAMITE)
            .map(([valor, texto]) => h("option", { value: valor }, texto))),
          h("label", { for: "f_referencia" }, "Referencia (opcional)"),
          h("input", { id: "f_referencia", maxlength: "60" }),
          h("label", { for: "f_archivo" }, "Archivo"),
          h("input", { id: "f_archivo", type: "file", accept: ".pdf,.png,.jpg,.jpeg", required: "" }));
        f.append(campos, h("div", { class: "acciones" }, h("button", { type: "submit" }, "Adjuntar")));
        f.addEventListener("submit", async (ev) => {
          ev.preventDefault();
          const archivo = $("#f_archivo").files[0];
          if (!archivo) return;
          const cuerpo = new FormData();
          cuerpo.append("titulo", $("#f_titulo").value);
          cuerpo.append("tramite", $("#f_tramite").value);
          cuerpo.append("referencia", $("#f_referencia").value);
          cuerpo.append("archivo", archivo);
          try {
            const r = await fetch("/api/documentos/adjuntar", { method: "POST", body: cuerpo,
              headers: { Authorization: "Bearer " + estado.token } });
            const j = await r.json();
            if (!r.ok) throw new Error(j.detail || "No se pudo adjuntar");
            salida.prepend(aviso("ok", "Documento adjuntado al expediente."));
            f.reset(); cargar();
          } catch (e) { salida.prepend(aviso("error", e.message)); }
        });
        return f;
      })()), salida, lista);
    cargar().catch((e) => lista.append(aviso("error", e.message)));
  } },
  alertas: { titulo: "Mis alertas", sub: "Sus próximos vencimientos y la suscripción a avisos", panel: true, render(raiz) {
    const bandeja = h("div", { class: "card" });
    const cargarBandeja = async () => {
      const ns = await api("/api/alertas/notificaciones", { auth: true });
      bandeja.replaceChildren(h("h2", {}, "Notificaciones"), ns.length
        ? tabla(["Asunto", "Trámite", "Referencia", "Recibida", "Estado", ""], ns.map((n) => [
            n.asunto, etiquetaTramite(n.tramite), n.referencia || "—", n.creada.slice(0, 10),
            h("span", { class: "chip " + (n.leida ? "programado" : "proximo") }, n.leida ? "Leída" : "Nueva"),
            n.leida ? "" : h("button", { type: "button", class: "sec", onclick: async () => {
              try { await api(`/api/alertas/notificaciones/${n.id}/leida`, { metodo: "POST", auth: true }); cargarBandeja(); }
              catch (e) { bandeja.prepend(aviso("error", e.message)); }
            } }, "Marcar leída"),
          ]))
        : "No tiene notificaciones.");
    };
    const salida = h("div", {}), venc = h("div", { class: "card" }, h("h2", {}, "Mis próximos vencimientos"), "Cargando…");
    raiz.append(bandeja, venc, h("div", { class: "card" }, h("h2", {}, "Suscripción a alertas"), formulario([
      { n: "canal", l: "Canal", opciones: CANALES }, { n: "contacto", l: "Correo o teléfono de contacto" },
      { n: "anticipacion_dias", l: "Avisar con (días de anticipación)", t: "number", v: 3, min: 1, max: 15 }], "Guardar", async (d, out) => {
      await api("/api/alertas/suscripcion", { metodo: "PUT", cuerpo: { canales: [d.canal], anticipacion_dias: d.anticipacion_dias, contacto: { [d.canal]: d.contacto } }, auth: true });
      out.append(aviso("ok", "Suscripción guardada."));
    }, salida)), salida);
    api("/api/alertas/mis-vencimientos", { auth: true }).then((r) => venc.replaceChildren(h("h2", {}, "Mis próximos vencimientos"),
      tablaVencimientos(r.vencimientos)))
      .catch((e) => venc.append(aviso("error", e.message)));
    cargarBandeja().catch((e) => bandeja.append(aviso("error", e.message)));
  } },
};

// ---- Sesión y navegación -----------------------------------------------------
const PUBLICAS = ["inicio", "calendario", "simulador", "fracc"];
const PRIVADAS = ["ficha", "rhe", "pagos", "declaracion", "expediente", "alertas"];

function cerrarSesion() {
  estado.token = estado.ruc = null; sessionStorage.clear();
  if (estado.vista === "login" || !vistas[estado.vista].publica) estado.vista = "inicio";
  pintar();
}

function irA(vista) {
  estado.vista = vista;
  cerrarCajon(false);
  pintar();
  const centro = $("#main");
  // Sin preventScroll el navegador desplaza el marco para "acercar" el elemento enfocado,
  // y como el marco está anclado al viewport la cabecera se perdía de vista.
  centro.focus({ preventScroll: true });
  centro.scrollTo({ top: 0 });
  const panel = $("#panel");
  if (panel) panel.scrollTop = 0;
}

// ---- Cajón lateral en móvil --------------------------------------------------
let cajonAbierto = false;
function abrirCajon() {
  cajonAbierto = true;
  $("#barra").classList.add("abierta");
  $("#velo").hidden = false;
  $("#abrir-menu").setAttribute("aria-expanded", "true");
  const primero = $("#menu .nav-item");
  if (primero) primero.focus({ preventScroll: true });
}
function cerrarCajon(devolverFoco) {
  if (!cajonAbierto) return;
  cajonAbierto = false;
  $("#barra").classList.remove("abierta");
  $("#velo").hidden = true;
  $("#abrir-menu").setAttribute("aria-expanded", "false");
  if (devolverFoco) $("#abrir-menu").focus({ preventScroll: true });
}

function vistaLogin(raiz) {
  const salida = h("div", {});
  let mfaToken = null;
  const paso1 = formulario([{ n: "ruc", l: "RUC (11 dígitos)", im: "numeric", p: "\\d{11}", ac: "username" }, { n: "usuario", l: "Usuario" }, { n: "clave", l: "Clave", t: "password", ac: "current-password" }], "Continuar", async (d, out) => {
    const r = await api("/api/auth/login", { metodo: "POST", cuerpo: d }); mfaToken = r.mfa_token; estado.rucTmp = d.ruc;
    paso2c.hidden = false; paso1c.hidden = true; out.append(aviso("info", r.mensaje));
  }, salida);
  const paso2 = formulario([{ n: "codigo", l: "Código de 6 dígitos", im: "numeric", p: "\\d{6}", ac: "one-time-code" }], "Verificar", async (d) => {
    const r = await api("/api/auth/mfa", { metodo: "POST", cuerpo: { mfa_token: mfaToken, codigo: d.codigo } });
    estado.token = r.access_token; estado.ruc = r.ruc; sessionStorage.setItem("token", r.access_token); sessionStorage.setItem("ruc", r.ruc);
    estado.vista = "ficha"; pintar();
  }, salida);
  const paso1c = h("div", { class: "card" }, h("h2", {}, "Ingreso con Clave SOL"), paso1);
  const paso2c = h("div", { class: "card", hidden: "" }, h("h2", {}, "Verificación en dos pasos"), paso2);
  raiz.append(paso1c, paso2c, salida);
}

function botonNav(clave) {
  return h("button", { type: "button", class: "nav-item", "data-vista": clave, "aria-label": vistas[clave].titulo,
    onclick: () => irA(clave) }, icono(clave), h("span", { class: "etiqueta" }, vistas[clave].titulo));
}

let firmaNav = null;
function construirNav() {
  const menu = $("#menu");
  const firma = estado.token ? "privado" : "publico";
  if (firma !== firmaNav) {                       // el menú solo se reconstruye si cambia la sesión
    firmaNav = firma;
    const hijos = [h("p", { class: "grupo" }, "Trámites públicos"), ...PUBLICAS.map(botonNav)];
    if (estado.token) hijos.push(h("p", { class: "grupo" }, "Mis trámites"), ...PRIVADAS.map(botonNav));
    menu.replaceChildren(...hijos);
  }
  for (const b of menu.querySelectorAll(".nav-item")) {
    if (b.dataset.vista === estado.vista) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  }
}

function pintarSesionLateral() {
  const hijos = [];
  if (estado.token) {
    hijos.push(h("div", { class: "ruc-lateral" }, "Sesión iniciada", h("b", {}, "RUC " + estado.ruc)));
    hijos.push(h("button", { type: "button", class: "nav-item", "aria-label": "Cerrar sesión", onclick: cerrarSesion },
      icono("salir"), h("span", { class: "etiqueta" }, "Salir")));
  } else {
    hijos.push(h("button", { type: "button", class: "nav-item", "aria-label": "Ingresar", onclick: () => irA("login") },
      icono("entrar"), h("span", { class: "etiqueta" }, "Ingresar")));
  }
  $("#sesion-lateral").replaceChildren(...hijos);
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
  "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

// Calendario del mes: resumen visual; el detalle accesible va en la lista de abajo.
function miniCalendario(marcados, hoy) {
  const anio = hoy.getFullYear(), mes = hoy.getMonth();
  const desplazamiento = (new Date(anio, mes, 1).getDay() + 6) % 7;   // lunes = 0
  const dias = new Date(anio, mes + 1, 0).getDate();
  const celdas = [];
  for (let i = 0; i < desplazamiento; i++) celdas.push(h("span", { class: "dia vacio" }, ""));
  for (let d = 1; d <= dias; d++) {
    const iso = `${anio}-${String(mes + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const clases = ["dia"];
    if (marcados.has(iso)) clases.push("marcado");
    if (d === hoy.getDate()) clases.push("hoy");
    celdas.push(h("span", { class: clases.join(" ") }, String(d)));
  }
  return h("div", { class: "mini", "aria-hidden": "true" },
    h("div", { class: "mini-sem" }, ["L", "M", "X", "J", "V", "S", "D"].map((d) => h("span", {}, d))),
    h("div", { class: "mini-dias" }, celdas));
}

function pintarPanel() {
  const panel = $("#panel"), cuerpo = $("#cuerpo");
  const v = vistas[estado.vista];
  const digito = estado.ruc ? Number(estado.ruc.slice(-1)) : estado.digito;
  if (!v || !v.panel || digito == null || !Number.isFinite(digito)) {
    panel.hidden = true; panel.replaceChildren(); cuerpo.classList.remove("con-panel");
    return;                                   // sin datos reales, la zona se oculta
  }
  cuerpo.classList.add("con-panel"); panel.hidden = false;
  api(`/api/alertas/calendario/${digito}`).then((r) => {
    const hoy = new Date();
    const marcados = new Set(r.vencimientos.map((x) => x.vence));
    const proximos = r.vencimientos.filter((x) => x.dias_restantes >= 0).slice(0, 5);
    panel.replaceChildren(
      h("div", { class: "panel-cab" },
        h("h3", { class: "mes" }, MESES[hoy.getMonth()] + " " + hoy.getFullYear()),
        h("span", { class: "panel-sub" }, "Dígito " + digito)),
      miniCalendario(marcados, hoy),
      h("div", { class: "panel-cab" }, h("h3", {}, "Próximos vencimientos"),
        h("button", { type: "button", class: "enlace", onclick: () => irA(estado.token ? "alertas" : "calendario") }, "Ver todo")),
      h("ul", { class: "panel-lista" }, proximos.length
        ? proximos.map((x) => h("li", {},
            h("span", { class: "pl-ic" }, icono("calendario", 15)),
            h("span", { class: "pl-txt" }, h("strong", {}, x.obligacion), h("span", {}, x.vence + " · " + x.periodo)),
            h("span", { class: "chip " + x.estado }, etiquetaEstado(x.estado))))
        : h("li", { class: "vacio" }, "Sin vencimientos próximos.")));
  }).catch(() => panel.replaceChildren(aviso("error", "No se pudo cargar el resumen.")));
}

function pintarCampana(contenedor) {
  if (!estado.token) return;
  const b = h("button", { type: "button", class: "icono-btn campana", "aria-label": "Mis vencimientos",
    onclick: () => irA("alertas") }, icono("alertas", 20));
  contenedor.prepend(b);
  Promise.all([
    api("/api/alertas/mis-vencimientos", { auth: true }).catch(() => ({ vencimientos: [] })),
    api("/api/alertas/notificaciones?solo_no_leidas=true", { auth: true }).catch(() => []),
  ]).then(([v, notifs]) => {
    const urgentes = (v.vencimientos || []).filter((x) => x.estado === "urgente" || x.estado === "vencido").length;
    const n = urgentes + notifs.length;
    if (n) {
      b.classList.add("con-aviso");
      const plural = (k, uno, varios) => `${k} ${k === 1 ? uno : varios}`;
      b.setAttribute("aria-label", `${plural(n, "aviso pendiente", "avisos pendientes")}: ${plural(urgentes, "vencimiento", "vencimientos")} y ${plural(notifs.length, "notificación", "notificaciones")}`);
    }
  }).catch(() => {});
}

function pintarCabecera() {
  const v = estado.vista === "login"
    ? { titulo: "Ingresar", sub: "Acceso con Clave SOL y verificación en dos pasos" }
    : vistas[estado.vista];
  $("#titulo-vista").textContent = v.titulo;
  $("#sub-vista").textContent = v.sub || "";
  document.title = v.titulo + " · Trámites tributarios";
  $("#cabecera-acciones").replaceChildren(estado.token
    ? h("div", { class: "usuario", "aria-label": "Sesión iniciada con el RUC " + estado.ruc },
        h("span", { class: "avatar", "aria-hidden": "true" }, estado.ruc.slice(-2)), h("span", {}, "RUC " + estado.ruc))
    : h("button", { type: "button", class: "sec", onclick: () => irA("login") }, "Ingresar"));
  pintarCampana($("#cabecera-acciones"));
}

function pintar() {
  construirNav();
  pintarSesionLateral();
  pintarCabecera();
  pintarPanel();
  const main = $("#main");
  main.replaceChildren();
  if (estado.vista === "login") vistaLogin(main); else vistas[estado.vista].render(main);
}

// ---- Arranque: el armazón (barra + cabecera) se construye una sola vez -------
$("#abrir-menu").append(icono("menu", 22));
$("#cerrar-menu").append(icono("cerrar", 20));
$("#abrir-menu").addEventListener("click", abrirCajon);
$("#cerrar-menu").addEventListener("click", () => cerrarCajon(true));
$("#velo").addEventListener("click", () => cerrarCajon(true));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") cerrarCajon(true); });
window.addEventListener("resize", () => { if (window.innerWidth > 760) cerrarCajon(false); });
pintar();
