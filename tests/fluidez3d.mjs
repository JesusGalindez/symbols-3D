// Fluidez del 3D con la GPU real (sin SwiftShader: Chrome headless usa la del Mac).
// (a) girar la vista 3D, (b) arrastrar una pieza en el 2D, (c)/(d) zoom con pellizco en
// 2D y 3D: fotogramas a ≤ 20 ms (p95); en (b) el 3D sigue al ratón, no espera a soltar.
// Uso:  npm run test:fluidez
import puppeteer from 'puppeteer-core';
import { arrancar, abrirEditor, puntoEnCapa, comprobar, resumen } from './comun.mjs';

const P95 = 20;
const e = await arrancar(8796);
await e.chrome.close();
e.chrome = await puppeteer.launch({ executablePath: process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new', defaultViewport: { width: 1500, height: 850 } });
try {
  const { p } = await abrirEditor(e.chrome, e.url, 'shou-circular');
  await p.waitForFunction(() => /Acabado real/.test(document.querySelector("#etiqueta3d").textContent));
  const gpu = await p.$eval('#tres canvas', (c) => { const gl = c.getContext('webgl2'); return gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL); });
  console.log(`GPU: ${gpu}`);
  const grabar = () => p.evaluate(() => { window.__t = []; window.__d = window.editor.dibujados3d(); const f = (t) => { window.__t.push(t); if (window.__grabando) requestAnimationFrame(f); }; window.__grabando = true; requestAnimationFrame(f); });
  const parar = () => p.evaluate(() => { window.__grabando = false; const t = window.__t, d = t.slice(1).map((v, i) => v - t[i]).sort((a, b) => a - b);
    const orden = t.slice(1).map((v, i) => v - t[i]), lentos = orden.map((v, i) => [i, v]).filter(([, v]) => v > 20);
    return { p95: d[Math.floor(d.length * 0.95)], lentos: lentos.map(([i, v]) => `#${i}:${v.toFixed(0)}`).join(' ') || 'ninguno', dibujados: window.editor.dibujados3d() - window.__d, cuadros: d.length }; });

  const [x, y] = await p.$eval('#tres canvas', (c) => { const r = c.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
  await grabar(); await p.mouse.move(x, y); await p.mouse.down();
  for (let i = 1; i <= 80; i++) await p.mouse.move(x + Math.sin(i / 8) * 150, y + Math.cos(i / 8) * 80);
  await p.mouse.up();
  const a = await parar();
  comprobar(a.p95 <= P95, `(a) girar la vista 3D: p95 ${a.p95.toFixed(1)} ms por fotograma · lentos (>20 ms): ${a.lentos}`);

  const pto = await puntoEnCapa(p);
  await p.mouse.move(...pto); await p.mouse.down();
  await grabar();
  for (let i = 1; i <= 60; i++) await p.mouse.move(pto[0] + i * 3, pto[1] + Math.sin(i / 6) * 20);
  const b = await parar();
  await p.mouse.up();
  comprobar(b.p95 <= P95, `(b) arrastrar la pieza grande en 2D: p95 ${b.p95.toFixed(1)} ms por fotograma · lentos (>20 ms): ${b.lentos}`);
  comprobar(b.dibujados >= b.cuadros * 0.8, `(b) el 3D sigue al arrastre: ${b.dibujados} dibujos 3D en ${b.cuadros} fotogramas`);
  await p.waitForFunction(() => /Acabado real/.test(document.querySelector("#etiqueta3d").textContent), { timeout: 30000 });
  comprobar(true, '(b) al soltar, la geometría exacta sustituye a la provisional');

  // (c) y (d) pellizco del trackpad: Chrome lo entrega como rueda con ⌃, varios eventos
  // por fotograma; se simula con ráfagas de 3 eventos por fotograma, acercar y alejar
  const pellizco = async ([px, py]) => {
    await p.mouse.move(px, py); await p.keyboard.down('Control');
    await grabar();
    for (let i = 0; i < 60; i++) {
      for (let k = 0; k < 3; k++) await p.mouse.wheel({ deltaY: i < 30 ? -4 : 4 });
      await p.evaluate(() => new Promise(requestAnimationFrame));
    }
    const r = await parar(); await p.keyboard.up('Control');
    return r;
  };
  const centro2d = await p.$eval('#lienzo', (c) => { const r = c.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
  const c = await pellizco(centro2d);
  comprobar(c.p95 <= P95, `(c) zoom con pellizco en 2D: p95 ${c.p95.toFixed(1)} ms por fotograma · lentos (>20 ms): ${c.lentos}`);
  const d = await pellizco([x, y]);
  comprobar(d.p95 <= P95, `(d) zoom con pellizco en 3D: p95 ${d.p95.toFixed(1)} ms por fotograma · lentos (>20 ms): ${d.lentos}`);

  // (e) suavidad del zoom 3D: un trackpad real manda los eventos a ráfagas irregulares
  // (0 en un fotograma, 4 en el siguiente). A 60 fps la cámara puede igualmente avanzar
  // a saltos; se mide el paso de la cámara por fotograma: su variación (desviación /
  // media de |Δ log distancia|) mientras dura el gesto. Suave = por debajo de 0,5.
  const rafagas = [0, 3, 1, 0, 4, 2, 0, 1, 3, 0, 0, 4, 1, 2, 0, 3];
  await p.mouse.move(x, y); await p.keyboard.down('Control');
  await p.evaluate(() => { window.__dist = []; window.__midiendo = true;
    const f = () => { window.__dist.push(window.editor.distancia3d()); if (window.__midiendo) requestAnimationFrame(f); }; requestAnimationFrame(f); });
  for (let i = 0; i < 48; i++) {
    for (let k = 0; k < rafagas[i % rafagas.length]; k++) await p.mouse.wheel({ deltaY: -3 });
    await p.evaluate(() => new Promise(requestAnimationFrame));
  }
  await new Promise((r) => setTimeout(r, 400));
  const pasos = await p.evaluate(() => { window.__midiendo = false; const v = window.__dist;
    return v.slice(1).map((d, i) => Math.abs(Math.log(d / v[i]))); });
  await p.keyboard.up('Control');
  const activos = pasos.slice(2, 44);  // mientras llegan eventos
  const media = activos.reduce((s, v) => s + v, 0) / activos.length;
  const cv = Math.sqrt(activos.reduce((s, v) => s + (v - media) ** 2, 0) / activos.length) / media;
  comprobar(cv < 0.5, `(e) zoom 3D con ráfagas irregulares: variación del paso de cámara ${cv.toFixed(2)} (suave < 0,5)`);
} finally {
  await e.parar();
}
process.exit(resumen());
