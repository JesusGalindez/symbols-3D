// Recorrido completo del editor en Chrome: mover, deshacer, escalar, rotar, dibujar,
// restar, nodos, geometría exacta, guardado automático, generar y nombres protegidos.
// Uso:  npm run test:ui     (código 1 si algo falla)
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { arrancar, abrirEditor, puntoEnCapa, comprobar, resumen } from './comun.mjs';

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
const e = await arrancar();
try {
  const { p, errores } = await abrirEditor(e.chrome, e.url, 'xi-doble');
  const campo = (n) => p.$eval(`[data-p=${n}]`, (x) => Number(x.value));
  const tecla = async (k, ...mods) => { for (const m of mods) await p.keyboard.down(m); await p.keyboard.press(k); for (const m of mods.reverse()) await p.keyboard.up(m); };
  const arrastrar = async ([x, y], [dx, dy]) => {
    await p.mouse.move(x, y); await p.mouse.down(); await p.mouse.move(x + dx / 2, y + dy / 2, { steps: 4 });
    await p.mouse.move(x + dx, y + dy, { steps: 4 }); await p.mouse.up();
  };
  const pantallaDe = (sel) => p.evaluate((s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }, sel);

  comprobar(await p.$$eval('#capas li', (l) => l.length) === 2, 'xi-doble abre con 2 capas');
  comprobar((await p.evaluate(() => window.editor.resultado().length)) === 2, 'la geometría exacta llega del servidor (2 piezas)');
  comprobar(errores.length === 0, `abre sin internet: ninguna petición fuera de localhost ${errores.join(' | ')}`);

  const pto = await puntoEnCapa(p);
  await p.mouse.click(...pto);
  await arrastrar(pto, [60, 0]);
  const x1 = await campo('x');
  comprobar(x1 > 0.05, `mover 60 px cambia X (${x1})`);
  comprobar(!(await p.evaluate(() => window.editor.exacta())), 'tras mover, la vista pasa a provisional');
  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
  comprobar(true, 'y vuelve a exacta sola tras la pausa');
  await tecla('z', 'Meta');
  comprobar(await campo('x') === 0, 'deshacer devuelve X a 0');
  await tecla('z', 'Meta', 'Shift');
  comprobar(await campo('x') === x1, 'rehacer vuelve a mover');

  await arrastrar(await pantallaDe('[data-asa="2"]'), [40, -40]);
  comprobar(await campo('w') > 1.0, `escalar desde la esquina agranda el ancho (${await campo('w')})`);
  await arrastrar(await pantallaDe('[data-asa="rot"]'), [80, 30]);
  comprobar(Math.abs(await campo('r')) > 5, `el asa de rotación gira (${await campo('r')}°)`);
  for (let i = 0; i < 3; i++) await tecla('z', 'Meta');
  const enNodos = () => p.$eval('#bNodos', (b) => b.classList.contains('activo'));
  const pto2 = await puntoEnCapa(p);
  await p.mouse.click(...pto2); await p.mouse.click(...pto2);
  comprobar(await enNodos(), 'doble clic sin mover abre los nodos');
  await p.keyboard.press('Escape');
  await p.mouse.click(...pto2); await arrastrar(pto2, [30, 0]);
  comprobar(!(await enNodos()), 'clic y arrastre rápido mueve, no abre los nodos');
  await tecla('z', 'Meta');

  const centro = await pantallaDe('#lienzo');
  await p.keyboard.press('Escape');
  await p.keyboard.press('r');
  await arrastrar([centro[0] - 250, centro[1] + 150], [500, 80]);
  await p.keyboard.press('o');
  await arrastrar([centro[0] - 60, centro[1] - 60], [120, 120]);
  await p.select('[data-p=op]', 'restar');
  const nombres = await p.$$eval('#capas li .nom', (l) => l.map((x) => x.textContent));
  comprobar(nombres.join() === 'Elipse 1,Rectángulo 1,Pieza 2,Pieza 1', `rectángulo y elipse nuevos arriba (${nombres})`);

  await p.click('#capas li:nth-child(2)');
  await p.keyboard.press('Enter');
  comprobar(await p.$$eval('#sobre .nodo', (l) => l.length) === 4, 'el rectángulo tiene 4 nodos');
  const n0 = await pantallaDe('#sobre .nodo');
  await arrastrar(n0, [-40, 40]);
  const nodo = await p.evaluate(() => window.editor.doc().capas.find((c) => c.nombre === 'Rectángulo 1').anillos[0][0]);
  comprobar(Math.abs(nodo[0] + 0.5) > 0.01, `arrastrar un nodo lo mueve (${nodo.map((v) => v.toFixed(3))})`);
  await p.keyboard.press('Escape');

  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
  const piezas = await p.evaluate(() => window.editor.resultado().length);
  comprobar(piezas >= 1, `geometría exacta tras la edición (${piezas} pieza(s))`);
  const huecoEnCentro = await p.evaluate(() => window.editor.resultado().some((poli) => poli.length > 1));
  comprobar(huecoEnCentro, 'la elipse que resta aparece como hueco en la geometría exacta');

  // guardado automático: la primera edición ya dejó el documento en disco
  const nombre = await p.$eval('#nombre', (x) => x.value);
  comprobar(existsSync(join(e.salida, 'editor', `${nombre}.json`)), `la primera edición se guardó sola en editor/${nombre}.json`);
  comprobar(readdirSync(join(e.salida, 'editor', '.historial', nombre)).length >= 1, 'y dejó copia en editor/.historial');

  await p.$eval('#nombre', (x) => { x.value = 'prueba-ui'; });
  await p.click('#bGenerar');
  await p.waitForFunction(() => !/Generando/.test(document.querySelector('#estado').textContent), { timeout: 120000 });
  const est = await p.$eval('#estado', (x) => x.textContent);
  comprobar(/malla cerrada/.test(est), `generar: ${est}`);
  comprobar(existsSync(join(e.salida, 'glb', 'prueba-ui.glb')), 'el GLB está en la carpeta temporal, no en glb/');
  await p.waitForFunction(() => /acabado exacto/.test(document.querySelector('#etiqueta3d').textContent), { timeout: 20000 });
  comprobar(true, 'la vista 3D muestra el GLB generado');

  await p.$eval('#nombre', (x) => { x.value = 'shou-cruz'; });
  await p.click('#bGenerar');
  await pausa(1500);
  comprobar(/no salió del editor/.test(await p.$eval('#estado', (x) => x.textContent)), 'no deja pisar shou-cruz, que está aprobado');
  await p.$eval('#nombre', (x) => { x.value = 'prueba-ui'; });  // como haría alguien tras el aviso

  // cuchilla (K): una línea vertical de lado a lado de «Pieza 1» la parte en capas;
  // cortar no cambia la forma, así que el área de la geometría exacta sigue igual
  const area = () => p.evaluate(() => window.editor.resultado().reduce((s, poli) => s + poli.reduce((t, a, k) => {
    let d = 0; for (let i = 0; i < a.length - 1; i++) d += a[i][0] * a[i + 1][1] - a[i + 1][0] * a[i][1];
    return t + (k ? -1 : 1) * Math.abs(d) / 2; }, 0), 0));
  await p.keyboard.press('Escape'); await p.keyboard.press('Escape');
  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
  const areaAntes = await area(), capasAntes = await p.$$eval('#capas li', (l) => l.length);
  const idPieza1 = await p.evaluate(() => window.editor.doc().capas.find((c) => c.nombre === 'Pieza 1').id);
  await p.click(`#capas li[data-id="${idPieza1}"]`);
  const bb = await p.$eval(`#lienzo path.capa[data-id="${idPieza1}"]`, (el) => { const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; });
  await p.keyboard.press('k');
  await p.mouse.click(bb[0] + bb[2] * 0.52, bb[1] - 15);
  await p.mouse.click(bb[0] + bb[2] * 0.52, bb[1] + bb[3] + 15);
  await p.keyboard.press('Enter');
  await p.waitForFunction((n) => document.querySelectorAll('#capas li').length > n, { timeout: 10000 }, capasAntes);
  const trasCorte = await p.$$eval('#capas li .nom', (l) => l.map((x) => x.textContent));
  comprobar(trasCorte.some((n) => n.startsWith('Pieza 1 · ')) && !trasCorte.includes('Pieza 1'),
    `la cuchilla parte «Pieza 1» en capas (${trasCorte.filter((n) => n.startsWith('Pieza 1')).join(', ')})`);
  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
  const areaDespues = await area();
  comprobar(Math.abs(areaDespues - areaAntes) < 1e-6, `cortar no cambia la forma (área ${areaAntes.toFixed(6)} → ${areaDespues.toFixed(6)})`);

  // cuchilla a mano alzada: arrastrar y soltar corta, aunque se empiece dentro del trazo
  // (la barra horizontal del centro de xi-doble va de y = -0,122 a -0,2)
  const nCapas = () => p.$$eval('#capas li', (l) => l.length);
  await p.keyboard.press('Escape'); await p.keyboard.press('Escape');
  let antesArrastre = await nCapas();
  const [ax0, ay0] = await p.evaluate(() => window.editor.aCliente(0, -0.09));
  const [ax1, ay1] = await p.evaluate(() => window.editor.aCliente(0, -0.24));
  await p.keyboard.press('k');
  await p.mouse.move(ax0, ay0); await p.mouse.down();
  await p.mouse.move(ax0 + 3, (ay0 + ay1) / 2, { steps: 8 }); await p.mouse.move(ax1, ay1, { steps: 8 }); await p.mouse.up();
  await p.waitForFunction((n) => document.querySelectorAll('#capas li').length > n, { timeout: 10000 }, antesArrastre);
  comprobar(true, `arrastrar con la cuchilla corta al soltar (${antesArrastre} → ${await nCapas()} capas)`);
  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
  comprobar(Math.abs(await area() - areaAntes) < 1e-6, 'y la forma sigue igual');
  antesArrastre = await nCapas();
  const [bx0, by0] = await p.evaluate(() => window.editor.aCliente(0.05, -0.16));  // dentro de la barra
  const [bx1, by1] = await p.evaluate(() => window.editor.aCliente(0.05, -0.24));
  await p.keyboard.press('k');
  await p.mouse.move(bx0, by0); await p.mouse.down(); await p.mouse.move(bx1, by1, { steps: 10 }); await p.mouse.up();
  await p.waitForFunction((n) => document.querySelectorAll('#capas li').length > n, { timeout: 10000 }, antesArrastre);
  comprobar(true, 'también si el arrastre empieza encima del trazo');
  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });

  // la cuchilla también termina con doble clic (el segundo clic no añade un punto repetido)
  const idPieza2 = await p.evaluate(() => window.editor.doc().capas.find((c) => c.nombre === 'Pieza 2').id);
  await p.click(`#capas li[data-id="${idPieza2}"]`);
  const bb2 = await p.$eval(`#lienzo path.capa[data-id="${idPieza2}"]`, (el) => { const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; });
  await p.keyboard.press('k');
  await p.mouse.click(bb2[0] - 15, bb2[1] + bb2[3] * 0.5);
  await p.mouse.click(bb2[0] + bb2[2] + 15, bb2[1] + bb2[3] * 0.5, { count: 2 });
  await p.waitForFunction(() => window.editor.doc().capas.some((c) => c.nombre.startsWith('Pieza 2 · ')), { timeout: 10000 });
  comprobar(true, 'la cuchilla termina con doble clic y parte «Pieza 2»');
  await p.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
  comprobar(Math.abs(await area() - areaAntes) < 1e-6, 'y la forma sigue igual');

  // costuras (shou-cruz): un corte que no separa se queda marcado y se suma al siguiente
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'shou-cruz');
    const cortarS = async (a, b) => {
      const [x0, y0] = await s.evaluate(([x, y]) => window.editor.aCliente(x, y), a);
      const [x1, y1] = await s.evaluate(([x, y]) => window.editor.aCliente(x, y), b);
      await s.keyboard.press('k');
      await s.mouse.move(x0, y0); await s.mouse.down(); await s.mouse.move(x1, y1, { steps: 10 }); await s.mouse.up();
      await s.waitForFunction(() => !/Cuchilla/.test(document.querySelector('#estado').textContent), { timeout: 10000 });
    };
    await cortarS([0, 0.56], [0, 0.38]);
    const tras1 = await s.evaluate(() => ({ n: window.editor.doc().capas.length, k: window.editor.doc().capas[0].costuras?.length }));
    comprobar(tras1.n === 1 && tras1.k === 1 && /Costura/.test(await s.$eval('#estado', (x) => x.textContent)),
      `un corte que no separa queda como costura y lo dice (${await s.$eval('#estado', (x) => x.textContent)})`);
    comprobar(await s.$$eval('#lienzo .costura', (l) => l.length) === 1, 'la costura se ve en el lienzo');
    await cortarS([0, -0.56], [0, -0.38]);
    const nombres = await s.$$eval('#capas li .nom', (l) => l.map((x) => x.textContent));
    comprobar(nombres.length === 2, `con el segundo corte se separa en dos (${nombres.join(', ')})`);
    comprobar(await s.$$eval('#lienzo .costura', (l) => l.length) === 0, 'y las costuras usadas desaparecen');
    await s.close();
  }

  // precisión de la cuchilla (shou-cruz): imán a los bordes rectos, recta al arrastrar y
  // Mayús para ángulos de 15°
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'shou-cruz');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    await s.keyboard.press('k');
    await s.waitForFunction(() => window.editor.bordes().length > 0, { timeout: 10000 });
    // el borde inferior de la barra derecha (x de 0,06 a 0,30): en el conector (x = 0,34),
    // 3 px por encima de su prolongación, el punto cae exactamente en ella
    const borde = await s.evaluate(() => window.editor.bordes().find(([a, b]) => Math.abs(a[1] - b[1]) < 1e-9 && a[1] > 0.03 && a[1] < 0.05 && Math.min(a[0], b[0]) > 0.05 && Math.max(a[0], b[0]) < 0.31));
    const [bx, by] = await cli(0.34, borde[0][1]);
    await s.mouse.move(bx, by - 3);  // 3 px por encima
    const marca = await s.evaluate(() => window.editor.marca());
    comprobar(marca && Math.abs(marca.p[1] - borde[0][1]) < 1e-12, `el imán deja el punto sobre la recta del borde (${marca?.p[1]} = ${borde[0][1]})`);
    // arrastre tembloroso de arriba abajo del anillo: la costura es una recta de 2 puntos
    const [x0, y0] = await cli(0, 0.56), [x1, y1] = await cli(0, 0.38);
    await s.mouse.move(x0, y0); await s.mouse.down();
    for (let i = 1; i <= 10; i++) await s.mouse.move(x0 + (i % 2 ? 6 : -6), y0 + (y1 - y0) * i / 10);
    await s.mouse.move(x1, y1); await s.mouse.up();
    await s.waitForFunction(() => window.editor.doc().capas[0].costuras?.length === 1, { timeout: 10000 });
    comprobar((await s.evaluate(() => window.editor.doc().capas[0].costuras[0].length)) === 2, 'arrastrar traza una recta de 2 puntos aunque la mano tiemble');
    // con Mayús, un arrastre algo torcido sale vertical exacto
    const [x2, y2] = await cli(0.005, -0.56), [x3, y3] = await cli(0.022, -0.38);  // 6° de la vertical (< 7,5°)
    let enviada = null;
    s.on('request', (r) => { if (r.url().endsWith('/api/cortar')) enviada = JSON.parse(r.postData()).linea; });
    await s.mouse.move(x2, y2); await s.keyboard.down('Shift'); await s.mouse.down();
    await s.mouse.move(x3, y3, { steps: 6 }); await s.mouse.up(); await s.keyboard.up('Shift');
    await s.waitForFunction(() => window.editor.doc().capas.length === 2, { timeout: 10000 });
    comprobar(enviada?.length === 2 && enviada[0][0] === enviada[1][0], `con Mayús, un arrastre algo torcido sale vertical exacto (x ${enviada?.map((q) => q[0]).join(' = ')})`);
    comprobar(true, 'y con la costura de arriba separa las dos mitades');
    await s.close();
  }

  // sugerencias de corte: en la cuchilla se ven las uniones; la barra superior derecha de
  // shou-cruz se suelta con tres clics (conector, tallo y anillo)
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'shou-cruz');
    await s.keyboard.press('k');
    await s.waitForFunction(() => document.querySelectorAll('#sobre .sugerencia').length > 0, { timeout: 10000 });
    comprobar(await s.$$eval('#sobre .sugerencia', (l) => l.length) === 40, 'al pulsar K se ven las 40 uniones sugeridas');
    const clicEnSugerencia = async (x, y) => {  // la sugerencia más cercana a (x, y) del mundo
      const [cx, cy] = await s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
      const punto = await s.$$eval('#sobre .sugerencia-toque', (ls, [cx, cy]) => {
        const r = document.querySelector('#sobre').getBoundingClientRect();
        const m = ls.map((l) => [r.left + (+l.getAttribute('x1') + +l.getAttribute('x2')) / 2, r.top + (+l.getAttribute('y1') + +l.getAttribute('y2')) / 2]);
        return m.sort((a, b) => Math.hypot(a[0] - cx, a[1] - cy) - Math.hypot(b[0] - cx, b[1] - cy))[0];
      }, [cx, cy]);
      const antes = await s.evaluate(() => JSON.stringify(window.editor.doc()));
      await s.mouse.click(...punto);
      await s.waitForFunction((a) => JSON.stringify(window.editor.doc()) !== a, { timeout: 10000 }, antes);
      await s.waitForFunction(() => document.querySelectorAll('#sobre .sugerencia').length > 0, { timeout: 10000 });
    };
    await clicEnSugerencia(0.34, 0.042);   // conector
    await clicEnSugerencia(0.12, 0.079);   // tallo
    await clicEnSugerencia(0.444, 0.109);  // anillo
    const areas = await s.evaluate(() => window.editor.doc().capas.map((c) => {
      let d = 0; const a = c.anillos[0];
      for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return Math.abs(d / 2) * Math.abs(c.t.sx * c.t.sy);
    }));
    comprobar(areas.some((a) => Math.abs(a - 0.0253) < 5e-4), `tres clics sueltan la barra (${areas.map((a) => a.toFixed(4)).join(', ')})`);
    comprobar(await s.$eval('[data-herr="cuchilla"]', (b) => b.classList.contains('activo')), 'la cuchilla sigue activa entre clics');
    await s.close();
  }

  // zoom con pellizco (⌃ + rueda): durante el gesto el lienzo va escalado por CSS; tiene
  // que coincidir con lo que se redibuja al acabar, y el punto bajo el cursor no se mueve
  const cajaCapa = () => p.$eval('#lienzo path.capa', (el) => { const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; });
  await p.mouse.move(...centro);
  const b0 = await cajaCapa();
  await p.keyboard.down('Control');
  for (let i = 0; i < 20; i++) await p.mouse.wheel({ deltaY: -5 });
  await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  const b1 = await cajaCapa();
  await pausa(400);
  await p.keyboard.up('Control');
  const b2 = await cajaCapa();
  const k = b2[2] / b0[2];
  comprobar(k > 1.5, `el pellizco acerca la vista (×${k.toFixed(2)})`);
  comprobar(b1.every((v, i) => Math.abs(v - b2[i]) < 1), `la vista durante el gesto coincide con la redibujada (${b1.map(Math.round)} / ${b2.map(Math.round)})`);
  const esperado = [centro[0] + (b0[0] - centro[0]) * k, centro[1] + (b0[1] - centro[1]) * k];
  comprobar(Math.hypot(b2[0] - esperado[0], b2[1] - esperado[1]) < 1, 'el punto bajo el cursor se queda quieto al hacer zoom');

  // cerrar sin guardar y reabrir: lo del último segundo y medio llega por sendBeacon, como
  // parche (el documento, con las piezas cortadas, ya pasa de los 64 KB que admite)
  comprobar(await p.evaluate(() => JSON.stringify(window.editor.doc()).length) > 64 * 1024, 'el documento ya pasa de 64 KB');
  await pausa(2000);  // el guardado automático de 1,5 s deja en disco los cortes
  await p.keyboard.press('Escape');
  await p.click('#capas li:nth-child(1)');
  await p.keyboard.press('ArrowRight', { delay: 10 });
  const xAntes = await p.evaluate(() => window.editor.doc().capas.at(-1).t.x);
  await p.close({ runBeforeUnload: true });
  await pausa(800);
  const { p: q } = await abrirEditor(e.chrome, e.url, 'prueba-ui');
  const xDespues = await q.evaluate(() => window.editor.doc().capas.at(-1).t.x);
  comprobar(Math.abs(xAntes - xDespues) < 1e-12, `cerrar la pestaña sin guardar y reabrir conserva el último cambio (${xAntes} → ${xDespues})`);
} finally {
  await e.parar();
}
process.exit(resumen());
