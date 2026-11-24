/* ReyBasar: carrusel, galería, carrito (localStorage → WhatsApp) y Quiero vender */
const RB = (() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const pesos = n => "$" + Number(n).toLocaleString("es-MX");
  const CLAVE = "rb_carrito";

  const leer = () => { try { return JSON.parse(localStorage.getItem(CLAVE)) || []; } catch { return []; } };
  const guardar = c => { try { localStorage.setItem(CLAVE, JSON.stringify(c)); } catch {} contador(); };
  const cant = x => Math.max(1, +x.cantidad || 1);
  function contador() {
    const n = leer().reduce((s, x) => s + cant(x), 0), el = $("#cartN");
    if (el) { el.textContent = n; el.hidden = !n; }
  }

  function hero() {
    const h = $("#hero"); if (!h) return;
    const items = $$(".hero-item", h), infos = $$(".hero-info", h), n = items.length;
    let i = 0, t;
    const pintar = () => {
      const ancho = h.clientWidth, paso = Math.min(300, ancho * 0.32);
      items.forEach((el, k) => {
        let d = k - i; if (d > n / 2) d -= n; if (d < -n / 2) d += n;
        const lejos = Math.abs(d);
        el.style.transform = `translateX(calc(-50% + ${d * paso}px)) scale(${d ? 0.75 : 1})`;
        el.style.opacity = lejos > 2 ? 0 : d ? 0.55 : 1;
        el.style.zIndex = 10 - lejos;
        el.style.pointerEvents = d ? "none" : "";
      });
      infos.forEach((el, k) => el.hidden = k !== i);
    };
    const mover = d => { i = (i + d + n) % n; pintar(); reiniciar(); };
    const reiniciar = () => { clearInterval(t); if (n > 1) t = setInterval(() => mover(1), 5000); };
    $(".hero-flecha.izq", h).onclick = () => mover(-1);
    $(".hero-flecha.der", h).onclick = () => mover(1);
    let x0 = null;
    h.addEventListener("touchstart", e => x0 = e.touches[0].clientX, { passive: true });
    h.addEventListener("touchend", e => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) mover(dx < 0 ? 1 : -1); x0 = null; });
    addEventListener("resize", pintar);
    pintar(); reiniciar();
  }

  function banners() {
    const b = $("#banners"); if (!b) return;
    const items = $$(".banner", b), puntos = $$(".banners-puntos button", b);
    let i = 0, t;
    const ver = k => { i = (k + items.length) % items.length; items.forEach((el, j) => el.hidden = j !== i); puntos.forEach((p, j) => p.classList.toggle("on", j === i)); };
    const reiniciar = () => { clearInterval(t); t = setInterval(() => ver(i + 1), 10000); };
    puntos.forEach((p, k) => p.onclick = () => { ver(k); reiniciar(); });
    const iz = $(".banners-flecha.izq", b), de = $(".banners-flecha.der", b);
    if (iz) { iz.onclick = () => { ver(i - 1); reiniciar(); }; de.onclick = () => { ver(i + 1); reiniciar(); }; }
    let x0 = null;
    b.addEventListener("touchstart", e => x0 = e.touches[0].clientX, { passive: true });
    b.addEventListener("touchend", e => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; if (Math.abs(dx) > 40) { ver(i + (dx < 0 ? 1 : -1)); reiniciar(); } x0 = null; });
    reiniciar();
  }

  function galeria() {
    const g = $("#galeria"); if (!g) return;
    const imgs = $$(".galeria-principal img", g), mins = $$(".miniaturas button", g);
    let i = 0;
    const ver = k => { i = (k + imgs.length) % imgs.length; imgs.forEach((im, j) => im.hidden = j !== i); mins.forEach((b, j) => b.classList.toggle("on", j === i)); };
    mins.forEach(b => b.onclick = () => ver(+b.dataset.i));
    const iz = $(".gal-flecha.izq", g), de = $(".gal-flecha.der", g);
    if (iz) { iz.onclick = () => ver(i - 1); de.onclick = () => ver(i + 1); }
  }

  function agregar() {
    const b = $("#agregar"); if (!b) return;
    const max = +b.dataset.max || 1, inp = $("#cantidad");
    const enCarrito = () => (leer().find(x => x.id == b.dataset.id) || {}).cantidad || 0;
    const pintar = () => { const n = +enCarrito(); if (n) b.textContent = `EN TU CARRITO (${n}) · VER`; };
    pintar();
    b.onclick = () => {
      if (b.textContent.includes("VER") && (!inp || +enCarrito() >= max)) { location.href = "/carrito"; return; }
      const quiero = inp ? Math.max(1, Math.min(+inp.value || 1, max)) : 1;
      const c = leer(), i = c.findIndex(x => x.id == b.dataset.id);
      if (i >= 0) c[i].cantidad = Math.min(cant(c[i]) + quiero, max), c[i].max = max;
      else c.push({ ...b.dataset, cantidad: Math.min(quiero, max), max });
      guardar(c); pintar();
      if (inp) { inp.value = 1; if (+enCarrito() >= max) inp.disabled = true; }
    };
    if (inp && +enCarrito() >= max) inp.disabled = true;
  }

  function pintarCarrito(opc, revisado) {
    const { costo, gratisDesde, wa } = opc;
    const c = leer();
    $("#carritoVacio").hidden = !!c.length;
    $("#carritoLleno").hidden = !c.length;
    if (!c.length) return;
    // Las piezas son únicas: quitar las que ya se apartaron o vendieron
    if (!revisado) {
      fetch("/api/disponibles?ids=" + c.map(p => p.id).join(",")).then(r => r.json()).then(d => {
        if (ajustar(d.disponibles || {})) aviso("Algunas piezas ya no están disponibles en esa cantidad; ajustamos tu carrito.");
        pintarCarrito(opc, true);
      }).catch(() => {});
    }
    $("#carritoLista").innerHTML = c.map((p, k) => `
      <li>
        <a href="/producto/${p.slug}"><img src="${p.foto || "/static/img/conejo.png"}" alt=""></a>
        <div><a href="/producto/${p.slug}"><b>${p.nombre}</b></a><small>${p.sku}${p.talla ? " · Talla " + p.talla : ""}</small></div>
        <div class="c-cant">${(+p.max || 1) > 1 ? `<button data-k="${k}" data-d="-1" aria-label="Menos">−</button><span>${cant(p)}</span><button data-k="${k}" data-d="1" aria-label="Más" ${cant(p) >= (+p.max || 1) ? "disabled" : ""}>+</button>` : ""}
          <b>${pesos(p.precio * cant(p))}</b>${cant(p) > 1 ? `<small>${pesos(p.precio)} c/u</small>` : ""}</div>
        <button data-k="${k}" class="c-quitar" aria-label="Quitar">✕</button>
      </li>`).join("");
    $$("#carritoLista .c-quitar").forEach(b => b.onclick = () => { const n = leer(); n.splice(+b.dataset.k, 1); guardar(n); pintarCarrito(opc, true); });
    $$("#carritoLista .c-cant button").forEach(b => b.onclick = () => {
      const n = leer(), it = n[+b.dataset.k], nueva = cant(it) + +b.dataset.d;
      if (nueva < 1) n.splice(+b.dataset.k, 1); else it.cantidad = Math.min(nueva, +it.max || 1);
      guardar(n); pintarCarrito(opc, true);
    });
    const sub = c.reduce((s, p) => s + p.precio * cant(p), 0);
    const env = gratisDesde && sub >= gratisDesde ? 0 : costo;
    $("#cSub").textContent = pesos(sub);
    $("#cEnvio").textContent = env ? pesos(env) : (costo ? "Gratis" : "Por acordar");
    $("#cTotal").textContent = pesos(sub + env);

    const f = $("#cForm"); if (!f || f.dataset.listo) return;
    f.dataset.listo = 1;
    f.onsubmit = async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f));
      const btn = $("#cEnviar"); btn.disabled = true; btn.textContent = "ENVIANDO…";
      try {
        const r = await fetch("/api/pedidos", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...d, items: leer().map(p => ({ id: +p.id, cantidad: cant(p) })) }) });
        const j = await r.json();
        if (r.ok) { guardar([]); location.href = j.url; return; }
        if (j.login) { location.href = "/cuenta/entrar?siguiente=/carrito"; return; }
        if (j.disponibles) { ajustar(j.disponibles); aviso(j.error); pintarCarrito(opc, true); }
        else aviso(j.error || "No se pudo hacer el pedido.");
      } catch { aviso("No hay conexión. Inténtalo de nuevo."); }
      btn.disabled = false; btn.textContent = "HACER PEDIDO";
    };
  }

  function aviso(txt) { const a = $("#cAviso"); if (a) { a.textContent = txt; a.hidden = false; scrollTo(0, 0); } }
  // Ajusta cantidades a lo disponible; devuelve true si cambió algo
  function ajustar(disp) {
    let cambio = false;
    const n = leer().filter(p => {
      if (!(p.id in disp)) return true;
      const max = +disp[p.id];
      if (max <= 0) { cambio = true; return false; }
      if (cant(p) > max) { p.cantidad = max; cambio = true; }
      p.max = max;
      return true;
    });
    guardar(n);
    return cambio;
  }

  function vender(wa) {
    $("#formVender").onsubmit = e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target));
      const txt = `Hola ReyBasar, quiero vender:\nNombre: ${d.nombre}\nTeléfono: ${d.tel}\nQué: ${d.tipo}\nPiezas aprox.: ${d.piezas}\nOpción: ${d.opcion}` + (d.comentario ? `\nComentarios: ${d.comentario}` : "");
      open(`https://wa.me/${wa}?text=${encodeURIComponent(txt)}`, "_blank");
    };
  }

  document.addEventListener("DOMContentLoaded", () => { contador(); hero(); banners(); galeria(); agregar(); });
  return { pintarCarrito, vender };
})();
