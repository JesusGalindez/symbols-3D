// Recorrido completo del editor en Chrome: mover, deshacer, escalar, rotar, dibujar,
// restar, nodos, geometría exacta, guardado automático, generar y nombres protegidos.
// Uso:  npm run test:ui     (código 1 si algo falla)
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
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
  // la vista 3D acaba mostrando la malla real (la de «Generar»), no una aproximación
  await p.waitForFunction(() => /Acabado real/.test(document.querySelector('#etiqueta3d').textContent), { timeout: 30000 });
  const tri3d = await p.evaluate(() => window.editor.triangulos3d());
  await p.$eval('#nombre', (x) => { x.value = 'paridad-3d'; });
  await p.click('#bGenerar');
  await p.waitForFunction(() => /triángulos/.test(document.querySelector('#estado').textContent), { timeout: 60000 });
  const triGlb = Number((await p.$eval('#estado', (x) => x.textContent)).match(/([\d.]+) triángulos/)[1].replace(/\./g, ''));
  comprobar(tri3d === triGlb, `la vista 3D es la malla real: ${tri3d} triángulos, los mismos que el GLB generado (${triGlb})`);

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
  const nodo = await p.evaluate(() => window.editor.doc().capas.find((c) => c.nombre === 'Rectángulo 1').anillos[0][0].p);
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
  comprobar(/APROBADO/.test(est), `generar: ${est}`);
  const tres = ['glb/prueba-ui.glb', 'glb/prueba-ui-ligera.glb', 'glb/web/prueba-ui-ligera.glb'];
  comprobar(tres.every((f) => existsSync(join(e.salida, f))), 'las tres versiones (detallada, ligera y web) están en la carpeta temporal, no en glb/');
  comprobar(await p.$$eval('.revision .pasa', (l) => l.length) === 6, 'y el panel lista las 6 comprobaciones en PASA');
  {
    const v = await e.chrome.newPage();
    await v.goto(e.url.replace('editor.html', 'visor.html?s=web/prueba-ui-ligera'));
    await v.waitForFunction(() => document.body.dataset.listo === '1', { timeout: 30000 });
    comprobar(true, 'el visor carga la versión web (meshopt)');
    await v.close();
  }
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

  // F2: imán al mover (un rectángulo nuevo, soltado a 3 px del eje, queda centrado en x = 0
  // exacto) y simetría en vivo (un hueco en la mitad izquierda sale también en la derecha)
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'xi-doble');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    await s.keyboard.press('r');
    const [r0x, r0y] = await cli(-0.25, -0.62), [r1x, r1y] = await cli(-0.1563, -0.68);  // bajo el símbolo; ancho 0,0937, que no alinea sus bordes con nada
    await s.mouse.move(r0x, r0y); await s.mouse.down(); await s.mouse.move(r1x, r1y, { steps: 4 }); await s.mouse.up();
    const rect = await s.evaluate(() => window.editor.doc().capas.at(-1));
    const [cx, cy] = await cli(rect.t.x, rect.t.y);
    const zoom = await s.evaluate(() => { const [a] = window.editor.aCliente(0, 0), [b] = window.editor.aCliente(1, 0); return b - a; });
    const [ex] = await cli(0, rect.t.y);
    await s.mouse.move(cx, cy); await s.mouse.down();
    await s.mouse.move((cx + ex) / 2, cy, { steps: 4 }); await s.mouse.move(ex + 1.5, cy, { steps: 4 });  // 1,5 px a la derecha del eje
    const guias = await s.evaluate(() => window.editor.guias().length);
    await s.mouse.up();
    const x = await s.evaluate(() => window.editor.doc().capas.at(-1).t.x);
    comprobar(guias > 0 && Math.abs(x) < 1e-12, `soltado a 1,5 px del eje queda en x = 0 exacto, con guía rosa (x = ${x}, ${guias} guía(s), 1 px = ${(1 / zoom).toFixed(4)})`);
    await s.keyboard.press('Escape');

    // imán en los nodos: una esquina del rectángulo, soltada a 3 px de una esquina de
    // xi-doble, queda exactamente encima
    await s.click(`#capas li[data-id="${rect.id}"]`);
    await s.keyboard.press('Enter');
    await s.waitForFunction(() => window.editor.exacta() && window.editor.bordes().length > 0, { timeout: 30000 });
    const destino = await s.evaluate((id) => window.editor.bordes().find(([, , c]) => c !== id)[0], rect.id);
    const nodo = await s.$eval('#sobre .nodo', (n) => { const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    const [dx, dy] = await cli(...destino);
    await s.mouse.move(...nodo); await s.mouse.down(); await s.mouse.move(dx + 3, dy - 2, { steps: 8 }); await s.mouse.up();
    const fin = await s.evaluate((id) => { const c = window.editor.doc().capas.find((k) => k.id === id), [u, v] = c.anillos[0][0].p;
      const co = Math.cos(c.t.r), si = Math.sin(c.t.r); return [c.t.x + co * u * c.t.sx - si * v * c.t.sy, c.t.y + si * u * c.t.sx + co * v * c.t.sy]; }, rect.id);
    comprobar(Math.hypot(fin[0] - destino[0], fin[1] - destino[1]) < 1e-12, `el nodo engancha exacto a la esquina de otra capa (${fin.map((v) => v.toFixed(6))} = ${destino.map((v) => v.toFixed(6))})`);
    await s.keyboard.press('Escape'); await s.keyboard.press('Escape');

    await s.select('[data-s=tipo]', 'lr');
    await s.waitForFunction(() => window.editor.doc().simetria?.lr, { timeout: 5000 });
    await s.keyboard.press('o');
    const [h0x, h0y] = await cli(-0.32, 0.12), [h1x, h1y] = await cli(-0.28, 0.08);
    await s.mouse.move(h0x, h0y); await s.mouse.down(); await s.mouse.move(h1x, h1y, { steps: 4 }); await s.mouse.up();
    await s.select('[data-p=op]', 'restar');
    comprobar(await s.$$eval('#lienzo .espejo-prov', (l) => l.length) === 1, 'la vista provisional muestra el reflejo de la mitad que manda');
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    const dentro = await s.evaluate(() => {
      const res = window.editor.resultado();
      const en = ([x, y]) => res.some((poli) => poli.reduce((n, a) => {
        let c = false; for (let i = 0, j = a.length - 1; i < a.length; j = i++) {
          if ((a[i][1] > y) !== (a[j][1] > y) && x < (a[j][0] - a[i][0]) * (y - a[i][1]) / (a[j][1] - a[i][1]) + a[i][0]) c = !c;
        } return n ^ c; }, false));
      let asimetricos = 0;  // 400 puntos al azar: dentro(p) == dentro(reflejo de p)
      for (let k = 0; k < 400; k++) { const p = [Math.random() - 0.5, Math.random() - 0.5]; if (en(p) !== en([-p[0], p[1]])) asimetricos++; }
      return { izq: en([-0.3, 0.1]), der: en([0.3, 0.1]), asimetricos };
    });
    comprobar(!dentro.izq && !dentro.der, 'con simetría izq. ↔ der., el hueco hecho a la izquierda sale en los dos lados');
    comprobar(dentro.asimetricos === 0, `y la geometría exacta es simétrica (${dentro.asimetricos} de 400 puntos distintos de su reflejo)`);
    await s.close();
  }

  // F3: selección múltiple. Criterio del plan: 3 capas con recuadro, girar 30°, escalar con
  // ⇧ y deshacer vuelve al JSON anterior idéntico; alinear al centro deja los tres centros
  // en el mismo X (< 1e-9). Y escalar sin proporción capas giradas hornea la cizalla.
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'xi-doble');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    const docTxt = () => s.evaluate(() => JSON.stringify(window.editor.doc()));
    const sel = () => s.evaluate(() => window.editor.seleccion().length);
    // puntos de cada capa en el mundo (el contorno aplanado, o solo sus nodos), y el centro de su caja
    const mundo = (soloNodos = false) => s.evaluate((soloNodos) => window.editor.doc().capas.map((c) => c.anillos.flatMap((r) =>
      (soloNodos ? r.map((n) => n.p) : window.editor.aplanar(r)).map(([u, v]) => {
        const co = Math.cos(c.t.r), si = Math.sin(c.t.r);
        return [c.t.x + co * u * c.t.sx - si * v * c.t.sy, c.t.y + si * u * c.t.sx + co * v * c.t.sy]; }))), soloNodos);
    const centrosX = async () => (await mundo()).map((P) => { const xs = P.map((q) => q[0]); return (Math.min(...xs) + Math.max(...xs)) / 2; });
    const asa = (q) => s.$eval(q, (n) => { const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });

    await s.keyboard.press('r');  // un rectángulo bajo el símbolo: tres capas
    const [r0x, r0y] = await cli(-0.3, -0.6), [r1x, r1y] = await cli(0.1, -0.7);
    await s.mouse.move(r0x, r0y); await s.mouse.down(); await s.mouse.move(r1x, r1y, { steps: 4 }); await s.mouse.up();
    const [a0x, a0y] = await cli(-0.62, 0.62), [a1x, a1y] = await cli(0.62, -0.78);
    await s.mouse.move(a0x, a0y); await s.mouse.down(); await s.mouse.move(a1x, a1y, { steps: 6 }); await s.mouse.up();
    comprobar(await sel() === 3, `el recuadro selecciona las 3 capas (${await sel()})`);
    comprobar(await s.$$eval('#contornos path', (l) => l.length) === 3 && await s.$$eval('#sobre .asa', (l) => l.length) === 5,
      'se ven sus 3 contornos y una caja común con 4 esquinas y el asa de giro');

    const antes = await docTxt(), r0 = await s.evaluate(() => window.editor.doc().capas.map((c) => c.t.r));
    // girar 30° con ⇧ (múltiplos de 15°): en pantalla, y hacia abajo, es -30°
    const [hx, hy] = await asa('#sobre .asa.rot');
    const [cx, cy] = await s.$eval('#sobre polygon.caja', (n) => { const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    const ang = Math.atan2(hy - cy, hx - cx) - Math.PI / 6, L = Math.hypot(hx - cx, hy - cy);
    await s.keyboard.down('Shift');
    await s.mouse.move(hx, hy); await s.mouse.down();
    await s.mouse.move(cx + L * Math.cos(ang), cy + L * Math.sin(ang), { steps: 8 }); await s.mouse.up();
    await s.keyboard.up('Shift');
    const giros = await s.evaluate((r0) => window.editor.doc().capas.map((c, i) => c.t.r - r0[i]), r0);
    comprobar(giros.every((g) => Math.abs(g - Math.PI / 6) < 1e-12), `girar con ⇧ gira las tres 30° exactos (${giros.map((g) => (g * 180 / Math.PI).toFixed(6)).join(', ')})`);

    const s0 = await s.evaluate(() => window.editor.doc().capas.map((c) => [c.t.sx, c.t.sy]));
    const [ex, ey] = await asa('#sobre .asa[data-asa="2"]');
    await s.keyboard.down('Shift');
    await s.mouse.move(ex, ey); await s.mouse.down(); await s.mouse.move(ex + 40, ey - 15, { steps: 6 }); await s.mouse.up();
    await s.keyboard.up('Shift');
    const ks = await s.evaluate((s0) => window.editor.doc().capas.flatMap((c, i) => [c.t.sx / s0[i][0], c.t.sy / s0[i][1]]), s0);
    comprobar(ks[0] > 1.05 && ks.every((k) => Math.abs(k - ks[0]) < 1e-12), `escalar con ⇧ escala las tres por igual, sin hornear (×${ks[0].toFixed(4)})`);
    await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.press('z'); await s.keyboard.up('Meta');
    comprobar(await docTxt() === antes, 'deshacer dos veces vuelve al JSON anterior idéntico');

    await s.click('[data-alinear="centro"]');
    const xs = await centrosX(), dx = Math.max(...xs) - Math.min(...xs);
    comprobar(dx < 1e-9, `alinear al centro deja los tres centros en el mismo X (diferencia ${dx.toExponential(1)})`);
    await s.click('[data-alinear="izq"]');
    const izq = (await mundo()).map((P) => Math.min(...P.map((q) => q[0])));
    comprobar(Math.max(...izq) - Math.min(...izq) < 1e-9, 'alinear a la izquierda iguala los bordes izquierdos');

    // girar 30° (rehecho a mano) y fijar el ancho de la selección ×1,5 en el panel: las capas
    // giradas no caben en (x, y, r, sx, sy), se hornean, y cada punto va a O + 1,5·(p − O) en X
    await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.press('z'); await s.keyboard.up('Meta');
    const [gx, gy] = await asa('#sobre .asa.rot');
    const [kx, ky] = await s.$eval('#sobre polygon.caja', (n) => { const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    const an = Math.atan2(gy - ky, gx - kx) - Math.PI / 6, Lg = Math.hypot(gx - kx, gy - ky);
    await s.keyboard.down('Shift'); await s.mouse.move(gx, gy); await s.mouse.down();
    await s.mouse.move(kx + Lg * Math.cos(an), ky + Lg * Math.sin(an), { steps: 8 }); await s.mouse.up(); await s.keyboard.up('Shift');
    const N0 = await mundo(true), P0 = await mundo(), W0 = Number(await s.$eval('[data-q=w]', (i) => i.value));
    const todos0 = P0.flat(), O = (Math.min(...todos0.map((q) => q[0])) + Math.max(...todos0.map((q) => q[0]))) / 2;
    await s.$eval('[data-q=w]', (i, v) => { i.value = v; i.dispatchEvent(new Event('change', { bubbles: true })); }, String(W0 * 1.5));
    const N1 = await mundo(true);  // los nodos: aplanar el contorno horneado no da los mismos puntos
    // W0 sale del panel con 3 decimales: la escala real es el ancho pedido entre el exacto
    const Wexacto = Math.max(...todos0.map((q) => q[0])) - Math.min(...todos0.map((q) => q[0])), kr = (W0 * 1.5) / Wexacto;
    let err = 0;
    N0.forEach((P, i) => P.forEach((q, j) => { err = Math.max(err, Math.abs(N1[i][j][0] - (O + kr * (q[0] - O))), Math.abs(N1[i][j][1] - q[1])); }));
    const ts = await s.evaluate(() => window.editor.doc().capas.map((c) => c.t));
    comprobar(err < 1e-9 && ts.every((t) => t.r === 0 && t.sx === 1 && t.sy === 1),
      `ancho ×1,5 con capas giradas: se hornea en los nodos y cada punto va donde toca (error ${err.toExponential(1)})`);
    // y lo mismo arrastrando una esquina sin ⇧: hornea al soltar y la geometría exacta llega
    await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta');
    const [qx, qy] = await asa('#sobre .asa[data-asa="2"]');
    await s.mouse.move(qx, qy); await s.mouse.down(); await s.mouse.move(qx + 60, qy - 5, { steps: 6 }); await s.mouse.up();
    const ts2 = await s.evaluate(() => window.editor.doc().capas.map((c) => c.t));
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    comprobar(ts2.every((t) => t.r === 0 && t.sx === 1) && /exacta/.test(await s.$eval('#etiqueta2d', (x) => x.textContent)),
      'arrastrar una esquina sin ⇧ también hornea y la geometría exacta llega');

    // ⇧ + clic en la lista quita una; ⌘A las vuelve a coger todas; ⌘D duplica las tres
    await s.keyboard.down('Shift'); await s.click('#capas li:first-child .nom'); await s.keyboard.up('Shift');
    comprobar(await sel() === 2, '⇧ + clic en la lista quita una de la selección');
    await s.keyboard.down('Meta'); await s.keyboard.press('a'); await s.keyboard.up('Meta');
    comprobar(await sel() === 3, '⌘A selecciona todas');
    await s.keyboard.down('Meta'); await s.keyboard.press('d'); await s.keyboard.up('Meta');
    comprobar((await s.evaluate(() => window.editor.doc().capas.length)) === 6 && await sel() === 3, '⌘D duplica las tres y deja seleccionadas las copias');
    await s.keyboard.press('Backspace');
    comprobar((await s.evaluate(() => window.editor.doc().capas.length)) === 3, 'Supr borra las tres copias');
    await s.close();
  }

  // F4: un documento de la versión 1 (puntos sueltos) se abre como nodos vivos y da la misma
  // forma; la elipse nueva es una curva de 4 nodos, no 128 puntos
  {
    writeFileSync(join(e.salida, 'editor', 'viejo.json'), JSON.stringify({ version: 1, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [{ id: 1, nombre: 'Cuadrado', op: 'unir', visible: true, anillos: [[[-0.2, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2]]], t: { x: 0, y: 0, r: 0, sx: 1, sy: 1 } }] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'viejo');
    const d = await s.evaluate(() => window.editor.doc());
    comprobar(d.version === 2 && d.capas[0].anillos[0].every((n) => n.tipo === 'vivo' && n.ent === null), 'un documento de la versión 1 se abre como nodos vivos (versión 2)');
    const area = await s.evaluate(() => window.editor.resultado().reduce((t, poli) => t + poli.reduce((u, a, k) => {
      let d = 0; for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return u + (k ? -1 : 1) * Math.abs(d / 2); }, 0), 0));
    comprobar(Math.abs(area - 0.16) < 0.001, `y el servidor saca la misma forma (área ${area.toFixed(4)}; 0,16 menos el redondeo de esquinas)`);
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    await s.keyboard.press('o');
    const [a0, b0] = await cli(0.25, 0.25), [a1, b1] = await cli(0.45, 0.05);
    await s.mouse.move(a0, b0); await s.mouse.down(); await s.mouse.move(a1, b1, { steps: 4 }); await s.mouse.up();
    const el = await s.evaluate(() => window.editor.doc().capas.at(-1).anillos[0]);
    comprobar(el.length === 4 && el.every((n) => n.ent && n.sal), 'la elipse nueva son 4 nodos con tiradores');
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    const r = await s.evaluate(() => window.editor.resultado().length);
    comprobar(r === 2, `y el servidor la aplana: 2 piezas en la geometría exacta (${r})`);
    await s.close();
  }

  // F4.3: pluma (un pétalo de 2 nodos, uno con curva), tiradores (espejo; ⌥ los separa),
  // doble clic en un nodo (esquina ↔ curva) y la cuchilla sobre una elipse (piezas con curvas)
  {
    // lo que quedó guardado del documento migrado: la versión 1 intacta o todo nodos, nunca
    // mezclado (un parche al cerrar rellenaba las capas sin cambios con los puntos del disco)
    const guardadoViejo = JSON.parse(readFileSync(join(e.salida, 'editor', 'viejo.json')));
    const formatos = new Set(guardadoViejo.capas.flatMap((c) => c.anillos.map((a) => Array.isArray(a[0]))));
    comprobar(formatos.size === 1, 'lo guardado de un documento migrado no mezcla puntos y nodos');
    const { p: s } = await abrirEditor(e.chrome, e.url, 'viejo');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    const ultima = () => s.evaluate(() => window.editor.doc().capas.at(-1));
    const area = () => s.evaluate(() => window.editor.resultado().reduce((t, poli) => t + poli.reduce((u, a, k) => {
      let d = 0; for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return u + (k ? -1 : 1) * Math.abs(d / 2); }, 0), 0));
    await s.keyboard.press('p');
    const A = await cli(-0.45, -0.45), B = await cli(-0.1, -0.3), B2 = await cli(-0.02, -0.12);
    await s.mouse.click(...A);
    await s.mouse.move(...B); await s.mouse.down(); await s.mouse.move(...B2, { steps: 5 }); await s.mouse.up();
    await s.mouse.click(...A);  // clic en el primero: cierra
    const petalo = await ultima();
    comprobar(petalo.nombre === 'Trazado 1' && petalo.anillos[0].length === 2 && petalo.anillos[0][1].tipo === 'espejo',
      `la pluma cierra un pétalo: 2 nodos, el segundo con curva (${petalo.nombre}, ${petalo.anillos[0].map((n) => n.tipo)})`);
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    comprobar(/exacta/.test(await s.$eval('#etiqueta2d', (x) => x.textContent)), 'y el servidor lo aplana sin error');

    await s.keyboard.press('o');
    const E0 = await cli(0.15, 0.15), E1 = await cli(0.45, 0.4);
    await s.mouse.move(...E0); await s.mouse.down(); await s.mouse.move(...E1, { steps: 4 }); await s.mouse.up();
    await s.keyboard.press('Enter');  // nodos
    const centro = async (q) => s.$eval(q, (n) => { const r = n.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await s.mouse.click(...await centro('#sobre .nodo[data-nodo="0,0"]'));
    comprobar(await s.$$eval('#sobre .tirador', (l) => l.length) === 4, 'un nodo elegido enseña sus 2 tiradores y los de sus vecinos que miran a él');
    const T = await centro('#sobre .tirador[data-tirador="0,0,sal"]');
    await s.mouse.move(...T); await s.mouse.down(); await s.mouse.move(T[0] + 25, T[1] - 15, { steps: 4 }); await s.mouse.up();
    let n0 = (await ultima()).anillos[0][0];
    comprobar(n0.ent[0] === -n0.sal[0] && n0.ent[1] === -n0.sal[1] && n0.tipo === 'espejo', 'arrastrar un tirador de un nodo espejo mueve el opuesto al revés');
    const salAntes = n0.sal, Te = await centro('#sobre .tirador[data-tirador="0,0,ent"]');
    await s.keyboard.down('Alt');
    await s.mouse.move(...Te); await s.mouse.down(); await s.mouse.move(Te[0] - 10, Te[1] + 20, { steps: 4 }); await s.mouse.up();
    await s.keyboard.up('Alt');
    n0 = (await ultima()).anillos[0][0];
    comprobar(n0.tipo === 'vivo' && n0.sal[0] === salAntes[0] && n0.sal[1] === salAntes[1], 'con ⌥ se separan: el nodo pasa a vivo y el otro tirador no se mueve');
    const N1 = await centro('#sobre .nodo[data-nodo="0,1"]');
    await s.mouse.click(...N1); await s.mouse.click(...N1);
    let n1 = (await ultima()).anillos[0][1];
    comprobar(n1.ent === null && n1.sal === null && n1.tipo === 'vivo', 'doble clic en un nodo curvo lo hace esquina');
    await new Promise((r) => setTimeout(r, 400));
    await s.mouse.click(...N1); await s.mouse.click(...N1);
    n1 = (await ultima()).anillos[0][1];
    comprobar(n1.tipo === 'suave' && n1.ent && n1.sal, 'y otro doble clic lo vuelve curva (suave)');
    await s.keyboard.press('Escape'); await s.keyboard.press('Escape');

    // la cuchilla parte la elipse por la mitad: dos piezas que siguen siendo curvas
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    const antes = await area(), nCapas = await s.evaluate(() => window.editor.doc().capas.length);
    await s.keyboard.press('k');
    const K0 = await cli(0.1, 0.27), K1 = await cli(0.5, 0.27);
    await s.mouse.move(...K0); await s.mouse.down(); await s.mouse.move(...K1, { steps: 6 }); await s.mouse.up();
    await s.waitForFunction((n) => window.editor.doc().capas.length === n + 1, { timeout: 10000 }, nCapas);
    const mitades = await s.evaluate(() => window.editor.doc().capas.slice(-2).map((c) => c.anillos[0]));
    comprobar(mitades.every((a) => a.length <= 6 && a.some((n) => n.ent || n.sal)),
      `la cuchilla parte la elipse en dos piezas con curvas (${mitades.map((a) => a.length).join(' y ')} nodos, no cientos)`);
    await s.keyboard.press('Escape');
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    const despues = await area();
    comprobar(Math.abs(despues - antes) < 1e-5, `y la forma sigue igual (área ${antes.toFixed(6)} → ${despues.toFixed(6)})`);
    await s.close();
  }

  // F5: un trazo de 0,01 de ancho no aguanta el canto → RECHAZADO: solo la detallada, para
  // mirarla, y fuera la ligera y la web de una generación anterior que sí pasó
  {
    const capa = (id, nombre, [x, y, w, h], visible = true) => ({ id, nombre, op: 'unir', visible, t: { x, y, r: 0, sx: 1, sy: 1 },
      anillos: [[[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map((p) => ({ p, ent: null, sal: null, tipo: 'vivo' }))] });
    writeFileSync(join(e.salida, 'editor', 'fino.json'), JSON.stringify({ version: 2, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [capa(1, 'Cuadrado', [0, 0, 0.4, 0.4]), capa(2, 'Trazo fino', [0, 0.35, 0.3, 0.01], false)] }));
    const { p: f } = await abrirEditor(e.chrome, e.url, 'fino');
    const generarYEsperar = async () => {
      await f.click('#bGenerar');
      await f.waitForFunction(() => !/Generando/.test(document.querySelector('#estado').textContent), { timeout: 120000 });
      return f.$eval('#estado', (x) => x.textContent);
    };
    const hay = (n) => existsSync(join(e.salida, n));
    comprobar(/APROBADO/.test(await generarYEsperar()) && hay('glb/fino-ligera.glb') && hay('glb/web/fino-ligera.glb'), 'con el trazo fino oculto: APROBADO y tres versiones');
    await f.click('#capas li[data-id="2"] .ojo');
    const est = await generarYEsperar();
    comprobar(/RECHAZADO/.test(est) && /trazo fino/.test(est), `con el trazo de 0,01 visible: ${est}`);
    comprobar(hay('glb/fino.glb') && !hay('glb/fino-ligera.glb') && !hay('glb/web/fino-ligera.glb'), 'solo queda la detallada: la ligera y la web de antes se borran');
    comprobar(await f.$eval('.revision .falla', (x) => x.textContent) === 'FALLA · trazo fino', 'y el panel marca la comprobación que falla');
    await f.close();
  }

  // F6: importar un SVG (Abrir → Importar SVG…), exportarlo, reordenar capas arrastrando,
  // deshacer con la selección, ⇧1 / ⇧0 y el panel de atajos (?)
  {
    const logo = join(e.salida, 'Logo Prueba.svg');
    writeFileSync(logo, `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 120">
      <style>.a{fill:#e30613}</style><circle class="a" cx="50" cy="60" r="40"/>
      <rect x="110" y="20" width="80" height="80" rx="12"/><path d="M0 0L200 120" fill="none"/>
      <path d="M100 110q20-30 40 0z"/></svg>`);
    const { p: s } = await abrirEditor(e.chrome, e.url, 'xi-doble');
    const [elegir] = await Promise.all([s.waitForFileChooser(), s.select('#abrir', '+importar')]);
    await elegir.accept([logo]);
    await s.waitForFunction(() => /Importado/.test(document.querySelector('#estado').textContent), { timeout: 10000 });
    const doc = await s.evaluate(() => window.editor.doc());
    comprobar(doc.capas.length === 3 && await s.$eval('#nombre', (x) => x.value) === 'logo-prueba',
      `importar un SVG: una capa por figura rellena, sin el trazo (${doc.capas.map((c) => c.nombre).join(', ')}) y nombre logo-prueba`);
    comprobar(doc.capas[0].anillos[0].length === 4 && doc.capas[0].anillos[0].every((n) => n.ent && n.sal), 'el círculo llega como 4 nodos con curvas');
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    comprobar(/exacta/.test(await s.$eval('#etiqueta2d', (x) => x.textContent)), 'y el servidor da su geometría exacta');
    const svg = await s.evaluate(() => window.editor.svgDiseno());
    comprobar(!svg.error && (svg.svg.match(/<path/g) ?? []).length === 3 && /C/.test(svg.svg), 'exportar SVG: una ruta con curvas por capa');

    const orden = () => s.$$eval('#capas li .nom', (l) => l.map((x) => x.textContent));
    const o0 = await orden();  // de arriba abajo
    const li = async (i) => s.$eval(`#capas li:nth-child(${i})`, (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y, r.height]; });
    const [ax, ay, ah] = await li(1), [, by, bh] = await li(3);
    await s.mouse.move(ax, ay + ah / 2); await s.mouse.down();
    await s.mouse.move(ax, by + bh * 0.8, { steps: 6 }); await s.mouse.up();
    const o1 = await orden();
    comprobar(o1.join() === [o0[1], o0[2], o0[0]].join(), `arrastrar la de arriba bajo la última la manda al fondo (${o0} → ${o1})`);
    comprobar((await s.evaluate(() => window.editor.seleccion().length)) === 0, 'soltar tras arrastrar no cambia la selección');

    // deshacer devuelve también la selección: se elige una, se mueve, se deselecciona y ⌘Z
    await s.click('#capas li:nth-child(2)');
    const id = await s.evaluate(() => window.editor.seleccion()[0]);
    await s.keyboard.press('ArrowRight');
    await s.keyboard.press('Escape');
    comprobar((await s.evaluate(() => window.editor.seleccion().length)) === 0, 'Esc suelta la selección');
    await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta');
    const tras = await s.evaluate(() => window.editor.seleccion());
    comprobar(tras.length === 1 && tras[0] === id, 'deshacer vuelve a seleccionar la capa que se había movido');
    await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta');
    comprobar((await s.$$eval('#capas li .nom', (l) => l.map((x) => x.textContent))).join() === o0.join(), 'y otro ⌘Z deshace el reordenado');

    // ⇧2 ajusta la selección al lienzo (⇧1, todo); ⇧0 vuelve al 100 %
    const escala = () => s.evaluate(() => { const [a] = window.editor.aCliente(0, 0), [b] = window.editor.aCliente(1, 0); return b - a; });
    await s.keyboard.press('Escape');
    const z0 = await escala();
    await s.click('#capas li:nth-child(3)');  // la más pequeña: el lóbulo
    await s.keyboard.down('Shift'); await s.keyboard.press('Digit2'); await s.keyboard.up('Shift');
    const z1 = await escala();
    comprobar(z1 > z0 * 2, `⇧2 ajusta la capa elegida al lienzo (zoom ×${(z1 / z0).toFixed(2)})`);
    await s.keyboard.down('Shift'); await s.keyboard.press('Digit1'); await s.keyboard.up('Shift');
    comprobar(Math.abs(await escala() / z0 - 1) < 0.3, `⇧1 ajusta todo (zoom ×${(await escala() / z0).toFixed(2)})`);
    await s.keyboard.down('Shift'); await s.keyboard.press('Digit0'); await s.keyboard.up('Shift');
    comprobar(Math.abs(await escala() - z0) < 1e-6, '⇧0 vuelve al 100 %');

    await s.keyboard.press('?');
    comprobar(!(await s.$eval('#ayuda', (x) => x.hidden)), '? abre el panel de atajos');
    await s.keyboard.press('Escape');
    comprobar(await s.$eval('#ayuda', (x) => x.hidden) && (await s.evaluate(() => window.editor.seleccion().length)) === 1,
      'Esc lo cierra sin soltar la selección');
    await s.close();
  }

  // G1: portapapeles (el SVG con el JSON de las capas dentro), pegar en su sitio, pegar un
  // SVG de fuera, ⌥ + arrastrar, ⌘D que repite, voltear, bloquear y Tab
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'xi-doble');
    const sel = () => s.evaluate(() => window.editor.seleccion());
    const capas = () => s.evaluate(() => window.editor.doc().capas);
    const copiar = (pg = s) => pg.evaluate(() => { const d = new DataTransfer(); document.dispatchEvent(new ClipboardEvent('copy', { clipboardData: d, bubbles: true })); return d.getData('text/plain'); });
    const pegar = async (texto, pg = s) => {
      const n = (await pg.evaluate(() => window.editor.doc().capas.length));
      await pg.evaluate((t) => { const d = new DataTransfer(); d.setData('text/plain', t); document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true })); }, texto);
      await pg.waitForFunction((n) => window.editor.doc().capas.length > n, { timeout: 10000 }, n);
    };
    const sinId = (cs) => JSON.stringify(cs.map(({ id, nombre, ...r }) => r));
    await s.keyboard.down('Meta'); await s.keyboard.press('a'); await s.keyboard.up('Meta');
    const originales = await capas(), texto = await copiar();
    comprobar(/^<svg/.test(texto) && /x-simbolos/.test(texto) && (texto.match(/<path/g) ?? []).length === 2, 'copiar pone un SVG con las 2 capas y su JSON dentro');
    const { p: otra } = await abrirEditor(e.chrome, e.url, 'shou-cruz');
    await pegar(texto, otra);
    const pegadas = (await otra.evaluate(() => window.editor.doc().capas)).slice(-2);
    comprobar(sinId(pegadas) === sinId(originales), 'pegarlo en otra pestaña da las mismas capas (salvo ids y nombres)');
    await otra.close();
    await pegar(texto);
    const desplazadas = (await capas()).slice(-2);
    comprobar(desplazadas.every((c, i) => Math.abs(c.t.x - originales[i].t.x - 0.02) < 1e-12), 'pegar encima de las originales las desplaza 0,02');
    await s.keyboard.down('Meta'); await s.keyboard.down('Shift'); await s.keyboard.press('v'); await s.keyboard.up('Shift'); await s.keyboard.up('Meta');
    await pegar(texto);
    const enSitio = (await capas()).slice(-2);
    comprobar(enSitio.every((c, i) => JSON.stringify(c.t) === JSON.stringify(originales[i].t)), '⇧⌘V las pega en su sitio (t idéntico)');

    // un SVG de fuera (el que exporta el editor de shou-cruz) en un documento vacío
    const ext = await s.evaluate(async () => { const r = await fetch('/api/abrir?s=shou-cruz').then((x) => x.json());
      const cs = r.doc.capas.map((c) => ({ ...c, anillos: c.anillos.map((a) => a.map((n) => ({ ...n, p: [n.p[0] + c.t.x, n.p[1] + c.t.y] }))) }));
      return (await fetch('/api/svg', { method: 'POST', body: JSON.stringify({ capas: cs, color: [0.6, 0.05, 0.03, 1] }) }).then((x) => x.json())).svg; });
    const { p: vacio } = await abrirEditor(e.chrome, e.url, 'xi-doble');
    await vacio.select('#abrir', '+nuevo');
    await vacio.waitForFunction(() => window.editor.doc().capas.length === 0);
    await pegar(ext, vacio);
    await vacio.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    const areaDe = (pg) => pg.evaluate(() => window.editor.resultado().reduce((t, poli) => t + poli.reduce((u, a, k) => {
      let d = 0; for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return u + (k ? -1 : 1) * Math.abs(d / 2); }, 0), 0));
    const { p: orig } = await abrirEditor(e.chrome, e.url, 'shou-cruz');
    const a0 = await areaDe(orig), a1 = await areaDe(vacio);
    comprobar(Math.abs(a1 / a0 - 1) < 0.002, `pegar el SVG de shou-cruz en un documento vacío da la misma forma (área ${a0.toFixed(5)} → ${a1.toFixed(5)})`);
    await orig.close(); await vacio.close();

    // ⌥ + arrastrar: exactamente una copia, y ⌘D repite su desplazamiento
    const n0 = (await capas()).length;
    await s.keyboard.press('Escape');
    const base = enSitio[0], pto = await puntoEnCapa(s, base.id);
    await s.mouse.click(...pto);
    await s.keyboard.down('Alt'); await s.mouse.move(...pto); await s.mouse.down();
    await s.mouse.move(pto[0] + 40, pto[1], { steps: 5 }); await s.mouse.up(); await s.keyboard.up('Alt');
    const trasAlt = await capas();
    comprobar(trasAlt.length === n0 + 1 && JSON.stringify(trasAlt.find((c) => c.id === base.id).t) === JSON.stringify(base.t),
      '⌥ + arrastrar crea una sola copia y el original no se mueve');
    const idC1 = (await sel())[0], c1 = trasAlt.find((c) => c.id === idC1);
    await s.keyboard.down('Meta'); await s.keyboard.press('d'); await s.keyboard.up('Meta');
    const idUlt = (await sel())[0], ult = (await capas()).find((c) => c.id === idUlt);
    comprobar(idUlt !== idC1 && Math.abs((ult.t.x - c1.t.x) - (c1.t.x - base.t.x)) < 1e-12 && Math.abs(c1.t.x - base.t.x) > 0.01,
      '⌘D tras ⌥ + arrastrar repite el mismo desplazamiento');

    // ⇧H dos veces vuelve a lo mismo; ⇧V refleja en vertical
    const antesV = JSON.stringify((await capas()).find((c) => c.id === ult.id).t);
    await s.keyboard.down('Shift'); await s.keyboard.press('h'); await s.keyboard.up('Shift');
    const volteada = (await capas()).find((c) => c.id === ult.id).t;
    comprobar(volteada.sx < 0, `⇧H voltea (sx = ${volteada.sx})`);
    await s.keyboard.down('Shift'); await s.keyboard.press('h'); await s.keyboard.up('Shift');
    const t2 = (await capas()).find((c) => c.id === ult.id).t, t1 = JSON.parse(antesV);
    comprobar(Object.keys(t1).every((k) => Math.abs(t2[k] - t1[k]) < 1e-12), '⇧H dos veces deja la capa como estaba');

    // bloquear: ni clic ni recuadro la eligen; Tab recorre las capas
    await s.keyboard.down('Meta'); await s.keyboard.down('Shift'); await s.keyboard.press('l'); await s.keyboard.up('Shift'); await s.keyboard.up('Meta');
    comprobar((await capas()).find((c) => c.id === ult.id).bloqueada === true && (await sel()).length === 0, '⇧⌘L bloquea y la suelta');
    const ptoB = await puntoEnCapa(s, ult.id);
    await s.mouse.click(...(ptoB ?? [0, 0]));
    comprobar(!(await sel()).includes(ult.id), 'un clic sobre una capa bloqueada no la elige');
    await s.keyboard.down('Meta'); await s.keyboard.press('a'); await s.keyboard.up('Meta');
    comprobar(!(await sel()).includes(ult.id), 'ni ⌘A');
    await s.keyboard.press('Escape');
    await s.click(`#capas li[data-id="${originales[0].id}"] .nom`);
    await s.keyboard.press('Tab');
    const orden = (await capas()).map((c) => c.id), i0 = orden.indexOf(originales[0].id);
    comprobar((await sel())[0] === orden[i0 + 1], 'Tab elige la capa de encima');
    await s.close();
  }

  // G2: caminos abiertos y trazos (pluma sin cerrar, alargar, grosor en el panel, caja con
  // el grosor, cuchilla sobre el esqueleto, contornear) y «Engrosar lo necesario»
  {
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    writeFileSync(join(e.salida, 'editor', 'trazos.json'), JSON.stringify({ version: 2, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] }, capas: [] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'trazos');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    const ultima = () => s.evaluate(() => window.editor.doc().capas.at(-1));
    await s.keyboard.press('p');
    for (const [x, y] of [[-0.3, 0.1], [0, 0.1], [0.2, 0.3]]) await s.mouse.click(...await cli(x, y));
    await s.keyboard.press('Escape');
    let c = await ultima();
    comprobar(c?.abierto === true && c.trazo?.ancho > 0 && c.anillos[0].length === 3, `Esc con 3 nodos deja un camino abierto con trazo (${c?.anillos?.[0].length} nodos)`);
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    comprobar(/exacta/.test(await s.$eval('#etiqueta2d', (x) => x.textContent)) && (await s.evaluate(() => window.editor.resultado().length)) === 1,
      'el servidor le da grosor: una pieza en la geometría exacta');
    // alargar desde el extremo final
    await s.keyboard.press('p');
    await s.mouse.click(...await cli(0.2, 0.3));
    await s.mouse.click(...await cli(0.4, 0.3));
    await s.keyboard.press('Enter');
    c = await ultima();
    comprobar(c.anillos[0].length === 4 && (await s.evaluate(() => window.editor.doc().capas.length)) === 1, 'clic en un extremo y otro punto alarga el mismo camino (4 nodos)');
    // grosor en el panel
    await s.$eval('[data-tr=ancho]', (i) => { i.value = '0.05'; i.dispatchEvent(new Event('change', { bubbles: true })); });
    comprobar((await ultima()).trazo.ancho === 0.05, 'el panel cambia el grosor');
    // caja con el grosor: un segmento horizontal de ancho 0,03 mide 0,03 de alto
    await s.keyboard.press('Escape'); await s.keyboard.press('p');
    await s.mouse.click(...await cli(-0.3, -0.3)); await s.mouse.click(...await cli(0.3, -0.3));
    await s.keyboard.press('Enter');
    comprobar(Math.abs(await s.$eval('[data-p=h]', (x) => Number(x.value)) - 0.03) < 1e-9, 'la caja de un segmento de grosor 0,03 mide 0,03 de alto');
    // la cuchilla lo parte por su esqueleto
    const n = await s.evaluate(() => window.editor.doc().capas.length);
    await s.keyboard.press('k');
    const [k0x, k0y] = await cli(0, -0.2), [k1x, k1y] = await cli(0, -0.4);
    await s.mouse.move(k0x, k0y); await s.mouse.down(); await s.mouse.move(k1x, k1y, { steps: 6 }); await s.mouse.up();
    await s.waitForFunction((n) => window.editor.doc().capas.length === n + 1, { timeout: 10000 }, n);
    const mitades = await s.evaluate(() => window.editor.doc().capas.slice(-2));
    comprobar(mitades.every((m) => m.abierto && m.trazo.ancho === 0.03 && m.anillos[0].length === 2), 'la cuchilla parte el trazo en dos trazos abiertos');
    // contornear (⇧⌘O)
    await s.keyboard.press('Escape'); await s.keyboard.press('Escape');
    await s.click(`#capas li[data-id="${mitades[0].id}"] .nom`);
    await s.keyboard.down('Meta'); await s.keyboard.down('Shift'); await s.keyboard.press('o'); await s.keyboard.up('Shift'); await s.keyboard.up('Meta');
    await s.waitForFunction((id) => !window.editor.doc().capas.find((c) => c.id === id).trazo, { timeout: 10000 }, mitades[0].id);
    const cont = await s.evaluate((id) => window.editor.doc().capas.find((c) => c.id === id), mitades[0].id);
    comprobar(!cont.abierto && cont.anillos[0].length >= 4, `⇧⌘O contornea: una forma rellena (${cont.anillos[0].length} nodos)`);
    await s.close();
  }
  {
    const cuadro = (id, nombre, [x, y, w, h]) => ({ id, nombre, op: 'unir', visible: true, t: { x, y, r: 0, sx: 1, sy: 1 },
      anillos: [[[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map((p) => ({ p, ent: null, sal: null, tipo: 'vivo' }))] });
    writeFileSync(join(e.salida, 'editor', 'fino2.json'), JSON.stringify({ version: 2, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [cuadro(1, 'Cuadrado', [0, 0, 0.4, 0.4]), cuadro(2, 'Trazo fino', [0, 0.35, 0.3, 0.01])] }));
    const { p: f } = await abrirEditor(e.chrome, e.url, 'fino2');
    const generar = async () => {
      await f.click('#bGenerar');
      await f.waitForFunction(() => !/Generando/.test(document.querySelector('#estado').textContent), { timeout: 120000 });
      return f.$eval('#estado', (x) => x.textContent);
    };
    comprobar(/RECHAZADO/.test(await generar()) && await f.$('#bEngrosar'), 'rechazado por trazo fino: el panel ofrece «Engrosar lo necesario»');
    await f.click('#bEngrosar');
    await f.waitForFunction(() => /Engrosadas/.test(document.querySelector('#estado').textContent), { timeout: 120000 });
    comprobar(/APROBADO/.test(await generar()), `tras engrosar lo necesario, APROBADO (${await f.$eval('#estado', (x) => x.textContent.slice(0, 40))})`);
    await f.close();
  }

  // G3: medir con ⌥, reglas y guías (que atraen como los ejes) y campos con operaciones
  {
    const cuadro = (id, nombre, [x, y, w, h]) => ({ id, nombre, op: 'unir', visible: true, t: { x, y, r: 0, sx: 1, sy: 1 },
      anillos: [[[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map((p) => ({ p, ent: null, sal: null, tipo: 'vivo' }))] });
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    writeFileSync(join(e.salida, 'editor', 'medir.json'), JSON.stringify({ version: 2, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      guias: { x: [0.137] }, capas: [cuadro(1, 'A', [-0.2, 0, 0.1, 0.1]), cuadro(2, 'B', [0.2, 0.013, 0.1, 0.1])] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'medir');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    await s.click('#capas li[data-id="1"] .nom');
    await s.mouse.move(...await cli(0.2, 0.02));
    await s.keyboard.down('Alt');
    const m1 = await s.evaluate(() => window.editor.medidas());
    comprobar(m1.length === 1 && Math.abs(m1[0].d - 0.3) < 1e-9, `⌥ mide la distancia entre las cajas (${m1.map((m) => m.d).join(', ')} = 0,3)`);
    await s.mouse.move(...await cli(-0.2, -0.35));
    const m2 = (await s.evaluate(() => window.editor.medidas())).map((m) => m.d).sort((a, b) => a - b);
    comprobar(m2.length === 4 && Math.abs(m2[0] - 0.25) < 1e-9 && Math.abs(m2[3] - 0.65) < 1e-9, `sin capa debajo, al círculo de diámetro 1 (${m2.map((v) => v.toFixed(3)).join(', ')})`);
    await s.keyboard.up('Alt');
    comprobar((await s.evaluate(() => window.editor.medidas())).length === 0, 'al soltar ⌥ se quitan');

    // la guía x = 0,137 atrae el centro de B soltado a 3 px
    const zoom = await s.evaluate(() => { const [a] = window.editor.aCliente(0, 0), [b] = window.editor.aCliente(1, 0); return b - a; });
    const [bx, by] = await cli(0.2, 0.013);
    await s.mouse.move(bx, by); await s.mouse.down();
    const [gx] = await cli(0.137, 0);
    await s.mouse.move((bx + gx) / 2, by, { steps: 4 }); await s.mouse.move(gx + 3, by, { steps: 4 }); await s.mouse.up();
    const xB = await s.evaluate(() => window.editor.doc().capas.find((c) => c.id === 2).t.x);
    comprobar(Math.abs(xB - 0.137) < 1e-12, `una guía en x = 0,137 atrae el centro soltado a 3 px (x = ${xB}; 1 px = ${(1 / zoom).toFixed(4)})`);
    // reglas: sacar una guía y devolverla a la regla
    await s.keyboard.press('Escape'); await s.keyboard.down('Shift'); await s.keyboard.press('r'); await s.keyboard.up('Shift');
    const rY = await s.$eval('#reglaY', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await s.mouse.move(...rY); await s.mouse.down(); await s.mouse.move(rY[0] + 200, rY[1], { steps: 5 }); await s.mouse.up();
    comprobar((await s.evaluate(() => window.editor.doc().guias.x.length)) === 2, '⇧R y arrastrar desde la regla izquierda saca una guía vertical');
    const g = await s.$eval('[data-guia="x,1"]', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await s.mouse.move(...g); await s.mouse.down(); await s.mouse.move(rY[0], g[1], { steps: 5 }); await s.mouse.up();
    comprobar((await s.evaluate(() => window.editor.doc().guias.x.length)) === 1, 'devuelta a la regla, se borra');

    // campos con operaciones
    await s.click('#capas li[data-id="1"] .nom');
    const campo = async (q, v) => s.$eval(`[data-p=${q}]`, (i, v) => { i.value = v; i.dispatchEvent(new Event('change', { bubbles: true })); }, v);
    const t = () => s.evaluate(() => window.editor.doc().capas.find((c) => c.id === 1).t);
    const x0 = (await t()).x;
    await campo('x', '+0,01');
    comprobar((await t()).x === x0 + 0.01, `«+0,01» en X suma exactamente 0,01 (${x0} → ${(await t()).x})`);
    await campo('x', '0,2*3');
    comprobar((await t()).x === 0.2 * 3, '«0,2*3» da 0,2 × 3');
    await campo('x', 'alert(1)');
    comprobar((await t()).x === 0.2 * 3, 'y «alert(1)» no cambia nada');
    await campo('w', '50%');
    comprobar(Math.abs((await t()).sx - 0.5) < 1e-12, '«50%» en el ancho lo deja a la mitad');
    comprobar(await s.evaluate(() => [window.editor.evaluar('(1+2)/4', 0), window.editor.evaluar('x', 0), window.editor.evaluar('*2', 3)].join()) === '0.75,NaN,6',
      'el evaluador: paréntesis, rechaza letras y *2 sobre lo actual');
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
      let d = 0; const a = window.editor.aplanar(c.anillos[0]);
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
  // parche. Con curvas los documentos ya son pequeños; los que pasan de los 64 KB que admite
  // son los densos de la versión 1 (lo guardado antes de F4): un círculo de 3000 puntos
  await p.close();
  writeFileSync(join(e.salida, 'editor', 'grande.json'), JSON.stringify({ version: 1, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
    capas: [{ id: 1, nombre: 'Disco', op: 'unir', visible: true, t: { x: 0, y: 0, r: 0, sx: 1, sy: 1 },
      anillos: [Array.from({ length: 3000 }, (_, i) => [0.4 * Math.cos(i * 2 * Math.PI / 3000), 0.4 * Math.sin(i * 2 * Math.PI / 3000)])] }] }));
  const { p: g } = await abrirEditor(e.chrome, e.url, 'grande');
  comprobar(await g.evaluate(() => JSON.stringify(window.editor.doc()).length) > 64 * 1024, 'el documento pasa de 64 KB');
  await pausa(2000);  // el guardado automático de 1,5 s deja en disco la versión migrada
  await g.click('#capas li:nth-child(1)');
  await g.keyboard.press('ArrowRight', { delay: 10 });
  const xAntes = await g.evaluate(() => window.editor.doc().capas.at(-1).t.x);
  await g.close({ runBeforeUnload: true });
  await pausa(800);
  const { p: q } = await abrirEditor(e.chrome, e.url, 'grande');
  const xDespues = await q.evaluate(() => window.editor.doc().capas.at(-1).t.x);
  comprobar(xAntes !== 0 && Math.abs(xAntes - xDespues) < 1e-12, `cerrar la pestaña sin guardar y reabrir conserva el último cambio (${xAntes} → ${xDespues})`);
} finally {
  await e.parar();
}
process.exit(resumen());
