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
    comprobar(d.version === 3 && d.capas[0].anillos[0].every((n) => n.tipo === 'vivo' && n.ent === null), 'un documento de la versión 1 se abre como nodos vivos (versión 3)');
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

  // G4: intersecar y excluir (panel, vista provisional y exacta), aplanar (⌘E) y los
  // botones booleanos (⌥⇧U)
  {
    const cuadro = (id, nombre, [x, y, w, h]) => ({ id, nombre, op: 'unir', visible: true, t: { x, y, r: 0, sx: 1, sy: 1 },
      anillos: [[[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map((p) => ({ p, ent: null, sal: null, tipo: 'vivo' }))] });
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    writeFileSync(join(e.salida, 'editor', 'bool.json'), JSON.stringify({ version: 2, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [cuadro(1, 'A', [-0.1, 0, 0.4, 0.4]), cuadro(2, 'B', [0.1, 0, 0.4, 0.4]), cuadro(3, 'C', [0, -0.35, 0.2, 0.1])] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'bool');
    const area = () => s.evaluate(() => window.editor.resultado().reduce((t, poli) => t + poli.reduce((u, a, k) => {
      let d = 0; for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return u + (k ? -1 : 1) * Math.abs(d / 2); }, 0), 0));
    const esperaExacta = () => s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    await s.click('#capas li[data-id="2"] .nom');
    await s.select('[data-p=op]', 'intersecar');
    comprobar(await s.$$eval('#lienzo .recorte', (l) => l.length) === 1, 'intersecar recorta lo de debajo en la vista provisional');
    await esperaExacta();
    const aI = await area();
    comprobar(Math.abs(aI - (0.2 * 0.4 + 0.2 * 0.1)) < 0.004, `intersecar: queda lo común de A y B, más C encima (área ${aI.toFixed(4)})`);
    await s.select('[data-p=op]', 'excluir');
    comprobar(/sin «excluir»/.test(await s.$eval('#etiqueta2d', (x) => x.textContent)), 'excluir se rotula en la provisional');
    await esperaExacta();
    const aE = await area();
    comprobar(Math.abs(aE - (0.4 * 0.4 + 0.02)) < 0.004, `excluir: A y B sin lo común, más C (área ${aE.toFixed(4)})`);
    // ⌘E con A y B (seguidas): una capa con la misma forma
    await s.keyboard.down('Shift'); await s.click('#capas li[data-id="1"] .nom'); await s.keyboard.up('Shift');
    await s.keyboard.down('Meta'); await s.keyboard.press('e'); await s.keyboard.up('Meta');
    await s.waitForFunction(() => window.editor.doc().capas.length === 2, { timeout: 10000 });
    await esperaExacta();
    comprobar(Math.abs(await area() - aE) < 1e-4, `⌘E aplana A y B en una capa con la misma forma (${(await area()).toFixed(4)})`);
    // ⌥⇧U: unir las dos que quedan
    await s.keyboard.down('Meta'); await s.keyboard.press('a'); await s.keyboard.up('Meta');
    await s.keyboard.down('Alt'); await s.keyboard.down('Shift'); await s.keyboard.press('KeyU'); await s.keyboard.up('Shift'); await s.keyboard.up('Alt');
    await s.waitForFunction(() => window.editor.doc().grupos?.length === 1, { timeout: 10000 });
    await esperaExacta();
    comprobar(Math.abs(await area() - aE) < 1e-4 && (await s.evaluate(() => window.editor.doc().grupos[0].booleana)) === 'unir', '⌥⇧U une las elegidas en un grupo booleano «Unión» (G5: no destructivo)');
    await s.close();
  }

  // G5: grupos (agrupar, elegir, entrar, ⌘ + clic, Esc, desagrupar, deshacer, grupo
  // booleano restar = restar las capas, arrastrar dentro y fuera en la lista)
  {
    const cuadro = (id, nombre, [x, y, w, h], r = 0) => ({ id, nombre, op: 'unir', visible: true, t: { x, y, r, sx: 1, sy: 1 },
      anillos: [[[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map((p) => ({ p, ent: null, sal: null, tipo: 'vivo' }))] });
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    writeFileSync(join(e.salida, 'editor', 'grupos.json'), JSON.stringify({ version: 2, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [cuadro(1, 'A', [-0.1, 0, 0.4, 0.4], 0.3), cuadro(2, 'B', [0.1, 0, 0.3, 0.3], -0.2), cuadro(3, 'C', [0.05, 0.05, 0.1, 0.1], 0.5), cuadro(4, 'Suelta', [0, -0.4, 0.2, 0.1])] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'grupos');
    const sel = () => s.evaluate(() => window.editor.seleccion());
    const docTxt = () => s.evaluate(() => JSON.stringify(window.editor.doc()));
    const mundoNodos = () => s.evaluate(() => window.editor.doc().capas.map((c) => c.anillos[0].map((n) => {
      const co = Math.cos(c.t.r), si = Math.sin(c.t.r), [u, v] = n.p; return [c.t.x + co * u * c.t.sx - si * v * c.t.sy, c.t.y + si * u * c.t.sx + co * v * c.t.sy]; })));
    const area = () => s.evaluate(() => window.editor.resultado().reduce((t, poli) => t + poli.reduce((u, a, k) => {
      let d = 0; for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return u + (k ? -1 : 1) * Math.abs(d / 2); }, 0), 0));
    const esperaExacta = () => s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    await esperaExacta();
    const aSueltas = await area(), antes = await docTxt(), n0 = await mundoNodos();
    for (const id of [1, 2, 3]) { await s.keyboard.down('Shift'); await s.click(`#capas li[data-id="${id}"] .nom`); await s.keyboard.up('Shift'); }
    await s.keyboard.down('Meta'); await s.keyboard.press('g'); await s.keyboard.up('Meta');
    const g = await s.evaluate(() => window.editor.doc().grupos?.[0]);
    comprobar(g && (await sel()).join() === String(g.id) && (await s.$$eval('#capas li.grupo', (l) => l.length)) === 1, '⌘G agrupa las tres y elige el grupo');
    await esperaExacta();
    comprobar(Math.abs(await area() - aSueltas) < 1e-9, 'un grupo normal de capas que unen no cambia la forma');
    // clic en el lienzo elige el grupo; doble clic entra; ⌘ + clic elige la capa; Esc sube
    await s.keyboard.press('Escape'); await s.keyboard.press('Escape');
    const pC = await puntoEnCapa(s, 3);
    await s.mouse.click(...pC);
    comprobar((await sel()).join() === String(g.id), 'clic en una capa del grupo elige el grupo');
    await s.mouse.click(...pC); await s.mouse.click(...pC);
    comprobar((await sel()).join() === '3', 'doble clic entra en el grupo y elige la capa');
    await s.keyboard.press('Escape');
    comprobar((await sel()).join() === String(g.id), 'Esc sube al grupo');
    await s.keyboard.press('Escape'); await s.keyboard.press('Escape');
    await s.keyboard.down('Meta'); await s.mouse.click(...pC); await s.keyboard.up('Meta');
    comprobar((await sel()).join() === '3', '⌘ + clic elige la capa directamente');
    // mover el grupo mueve sus tres capas; desagrupar deja cada nodo donde estaba
    await s.click(`#capas li[data-id="${g.id}"] .nom`);
    await s.keyboard.press('ArrowRight'); await s.keyboard.press('ArrowLeft');
    await s.keyboard.down('Meta'); await s.keyboard.down('Shift'); await s.keyboard.press('g'); await s.keyboard.up('Shift'); await s.keyboard.up('Meta');
    const n1 = await mundoNodos();
    let err = 0; n0.forEach((r, i) => r.forEach((q, j) => { err = Math.max(err, Math.hypot(q[0] - n1[i][j][0], q[1] - n1[i][j][1])); }));
    comprobar(!(await s.evaluate(() => window.editor.doc().grupos)) && err < 1e-12, `desagrupar deja cada nodo en su sitio (error ${err.toExponential(1)})`);
    // deshacer hasta antes de agrupar: el JSON idéntico
    for (let i = 0; i < 4; i++) { await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta'); }
    comprobar(await docTxt() === antes, 'deshacer vuelve al JSON de antes de agrupar');
    // grupo booleano «restar» = las capas sueltas con «restar»
    for (const id of [1, 2, 3]) { await s.keyboard.down('Shift'); await s.click(`#capas li[data-id="${id}"] .nom`); await s.keyboard.up('Shift'); }
    await s.keyboard.down('Alt'); await s.keyboard.down('Shift'); await s.keyboard.press('KeyS'); await s.keyboard.up('Shift'); await s.keyboard.up('Alt');
    await esperaExacta();
    const aGrupo = await area();
    for (let i = 0; i < 1; i++) { await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta'); }
    for (const id of [2, 3]) { await s.click(`#capas li[data-id="${id}"] .nom`); await s.select('[data-p=op]', 'restar'); }
    await esperaExacta();
    comprobar(Math.abs(await area() - aGrupo) < 1e-6, `un grupo booleano «restar» da lo mismo que restar las capas sueltas (${aGrupo.toFixed(6)})`);
    // arrastrar en la lista: «Suelta» dentro de un grupo nuevo de A y B, y otra vez fuera
    for (let i = 0; i < 2; i++) { await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta'); }
    await s.click('#capas li[data-id="1"] .nom'); await s.keyboard.down('Shift'); await s.click('#capas li[data-id="2"] .nom'); await s.keyboard.up('Shift');
    await s.keyboard.down('Meta'); await s.keyboard.press('g'); await s.keyboard.up('Meta');
    const gid = (await sel())[0];
    const fila = (id) => s.$eval(`#capas li[data-id="${id}"]`, (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y, r.height]; });
    const arrastrarFila = async (id, destino, frac) => {
      const [x, y, h] = await fila(id), [, y2, h2] = await fila(destino);
      await s.mouse.move(x, y + h / 2); await s.mouse.down(); await s.mouse.move(x, y2 + h2 * frac, { steps: 6 }); await s.mouse.up();
    };
    await arrastrarFila(4, gid, 0.8);  // mitad de abajo de un grupo desplegado: dentro
    comprobar((await s.evaluate(() => window.editor.doc().capas.find((c) => c.id === 4).grupo)) === gid, 'arrastrar a la mitad de abajo de un grupo la mete dentro');
    await arrastrarFila(4, gid, 0.2);  // mitad de arriba: encima, fuera
    comprobar((await s.evaluate(() => window.editor.doc().capas.find((c) => c.id === 4).grupo)) === undefined, 'y a la mitad de arriba la saca encima del grupo');
    await s.close();
  }

  // G6: radio de esquinas (capa y nodo), tipo de nodo en el panel y curvar con ⌘
  {
    const cuadro = (id, nombre, [x, y, w, h]) => ({ id, nombre, op: 'unir', visible: true, t: { x, y, r: 0, sx: 1, sy: 1 },
      anillos: [[[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map((p) => ({ p, ent: null, sal: null, tipo: 'vivo' }))] });
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    writeFileSync(join(e.salida, 'editor', 'esquinas.json'), JSON.stringify({ version: 3, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [cuadro(1, 'Cuadrado', [0, 0, 0.4, 0.4])] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'esquinas');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    const capa = () => s.evaluate(() => window.editor.doc().capas[0]);
    const area = () => s.evaluate(() => window.editor.resultado().reduce((t, poli) => t + poli.reduce((u, a, k) => {
      let d = 0; for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; }
      return u + (k ? -1 : 1) * Math.abs(d / 2); }, 0), 0));
    await s.click('#capas li[data-id="1"] .nom');
    await s.$eval('[data-radio=capa]', (i) => { i.value = '0.05'; i.dispatchEvent(new Event('change', { bubbles: true })); });
    comprobar((await capa()).anillos[0].every((n) => n.radio === 0.05), 'el radio de la capa va a sus cuatro esquinas');
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    // la exacta del servidor lleva además el redondeo del acabado (canto): se compara con la vista
    const plano = await s.evaluate(() => { const c = window.editor.doc().capas[0];
      const a = window.editor.aplanar(window.editor.redondear(c.anillos[0])); let d = 0;
      for (let i = 0; i < a.length; i++) { const p = a[i], q = a[(i + 1) % a.length]; d += p[0] * q[1] - q[0] * p[1]; } return Math.abs(d / 2); });
    comprobar(Math.abs(plano - (0.16 - (4 - Math.PI) * 0.0025)) < 2e-5 && Math.abs(await area() - plano) < 2e-3, `la vista y el servidor redondean las esquinas (área ${plano.toFixed(5)})`);
    // radio de un nodo y tipo de nodo desde el panel
    await s.keyboard.press('Enter');
    const n0 = await s.$eval('#sobre .nodo[data-nodo="0,0"]', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await s.mouse.click(...n0);
    await s.$eval('[data-radio=nodo]', (i) => { i.value = '0'; i.dispatchEvent(new Event('change', { bubbles: true })); });
    comprobar(!('radio' in (await capa()).anillos[0][0]) && (await capa()).anillos[0][1].radio === 0.05, 'el radio de un nodo se cambia solo en ese nodo');
    await s.select('[data-nodo-tipo]', 'espejo');
    const nt = (await capa()).anillos[0][0];
    comprobar(nt.tipo === 'espejo' && nt.ent && Math.abs(nt.ent[0] + nt.sal[0]) < 1e-12 && Math.abs(nt.ent[1] + nt.sal[1]) < 1e-12, 'el panel lo hace nodo espejo (tiradores opuestos e iguales)');
    // curvar el tramo de arriba (del nodo 2 al 3) con ⌘ + arrastrar: la curva pasa por el punto soltado
    const [a0x, a0y] = await cli(0, 0.2), [a1x, a1y] = await cli(0.03, 0.32);
    await s.keyboard.down('Meta'); await s.mouse.move(a0x, a0y); await s.mouse.down(); await s.mouse.move(a1x, a1y, { steps: 5 }); await s.mouse.up(); await s.keyboard.up('Meta');
    const soltado = await s.evaluate(([x, y]) => { const r = document.querySelector('#dos').getBoundingClientRect(), [ox] = window.editor.aCliente(0, 0), [x1] = window.editor.aCliente(1, 0);
      const [, oy] = window.editor.aCliente(0, 0); const z = x1 - ox; return [(x - ox) / z, -(y - oy) / z]; }, [a1x, a1y]);
    const d = await s.evaluate((m) => {
      const c = window.editor.doc().capas[0], r = c.anillos[0], a = r[2], b = r[3];
      const P = [a.p, [a.p[0] + a.sal[0], a.p[1] + a.sal[1]], [b.p[0] + b.ent[0], b.p[1] + b.ent[1]], b.p];
      const B = (t) => [0, 1].map((j) => (1 - t) ** 3 * P[0][j] + 3 * (1 - t) ** 2 * t * P[1][j] + 3 * (1 - t) * t * t * P[2][j] + t ** 3 * P[3][j]);
      const dist = (t) => { const q = B(t); return Math.hypot(q[0] + c.t.x - m[0], q[1] + c.t.y - m[1]); };
      let lo = 0, hi = 1; for (let i = 0; i < 200; i++) { const a = lo + (hi - lo) / 3, b = hi - (hi - lo) / 3; if (dist(a) < dist(b)) hi = b; else lo = a; }
      return dist((lo + hi) / 2);
    }, soltado);
    comprobar(d < 1e-9, `⌘ + arrastrar curva el tramo y pasa por el punto soltado (a ${d.toExponential(1)})`);
    await s.close();
  }

  // G7: varios nodos (marco y lazo), moverlos juntos, ⇧⌘M, ⌘J y el lápiz
  {
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    const poli = (id, nombre, n, [cx, cy], r, extra = {}) => ({ id, nombre, op: 'unir', visible: true, t: { x: cx, y: cy, r: 0, sx: 1, sy: 1 },
      anillos: [Array.from({ length: n }, (_, i) => ({ p: [r * Math.cos(i * 2 * Math.PI / n), r * Math.sin(i * 2 * Math.PI / n)], ent: null, sal: null, tipo: 'vivo' }))], ...extra });
    writeFileSync(join(e.salida, 'editor', 'nodos.json'), JSON.stringify({ version: 3, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] },
      capas: [poli(1, 'Dodecágono', 24, [0, 0.1], 0.3)] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'nodos');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    const capa = () => s.evaluate(() => window.editor.doc().capas[0]);
    await s.click('#capas li[data-id="1"] .nom'); await s.keyboard.press('Enter');
    // marco sobre la mitad derecha: 12 nodos (x > 0 en local; el de x = 0 no)
    const [m0x, m0y] = await cli(0.01, 0.5), [m1x, m1y] = await cli(0.5, -0.3);
    await s.mouse.move(m0x, m0y); await s.mouse.down(); await s.mouse.move(m1x, m1y, { steps: 6 }); await s.mouse.up();
    const n = await s.$$eval('#sobre .nodo.sel', (l) => l.length);
    comprobar(n === 11, `el marco elige los nodos de dentro (${n})`);
    const antes = (await capa()).anillos[0];
    const uno = await s.$eval('#sobre .nodo.sel', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await s.mouse.move(...uno); await s.mouse.down(); await s.mouse.move(uno[0] + 30, uno[1] - 10, { steps: 5 }); await s.mouse.up();
    const despues = (await capa()).anillos[0];
    const deltas = antes.map((q, i) => [despues[i].p[0] - q.p[0], despues[i].p[1] - q.p[1]]).filter(([dx, dy]) => dx || dy);
    const iguales = deltas.every(([dx, dy]) => Math.abs(dx - deltas[0][0]) < 1e-15 && Math.abs(dy - deltas[0][1]) < 1e-15);
    comprobar(deltas.length === 11 && iguales, `arrastrar uno mueve los 11 elegidos lo mismo (${deltas.length} movidos)`);
    // lazo (Q) alrededor de dos nodos vecinos, juntarlos y fusionarlos (⇧⌘M)
    await s.keyboard.press('q');
    const w = (i) => s.evaluate((i) => { const c = window.editor.doc().capas[0], n = c.anillos[0][i].p; return [c.t.x + n[0], c.t.y + n[1]]; }, i);
    const [p13, p14] = [await w(13), await w(14)];
    const cx = (p13[0] + p14[0]) / 2, cy = (p13[1] + p14[1]) / 2, R = 0.06;
    const lazo = []; for (let a = 0; a <= 2 * Math.PI + 0.01; a += Math.PI / 8) lazo.push(await cli(cx + R * Math.cos(a), cy + R * Math.sin(a)));
    await s.mouse.move(...lazo[0]); await s.mouse.down(); for (const q of lazo.slice(1)) await s.mouse.move(...q); await s.mouse.up();
    comprobar(await s.$$eval('#sobre .nodo.sel', (l) => l.length) === 2, 'el lazo elige los dos nodos de dentro');
    // a la vez a 0,0005 uno del otro: se escalan hacia su centro y se funden
    const esq = await s.$eval('#sobre .asa[data-asa-n="0"]', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    const opu = await s.$eval('#sobre .asa[data-asa-n="2"]', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    await s.mouse.move(...esq); await s.mouse.down(); await s.mouse.move(opu[0] - 0.2, opu[1] + 0.2, { steps: 8 }); await s.mouse.up();
    await s.keyboard.down('Meta'); await s.keyboard.down('Shift'); await s.keyboard.press('m'); await s.keyboard.up('Shift'); await s.keyboard.up('Meta');
    comprobar((await capa()).anillos[0].length === 23, `⇧⌘M funde los dos nodos juntos en uno (${(await capa()).anillos[0].length} nodos)`);
    await s.keyboard.press('Escape'); await s.keyboard.press('Escape');
    // ⌘J: dos caminos abiertos que se tocan se unen en uno
    await s.keyboard.press('p');
    for (const [x, y] of [[-0.4, -0.4], [-0.1, -0.4]]) await s.mouse.click(...await cli(x, y));
    await s.keyboard.press('Enter');
    const id1 = (await s.evaluate(() => window.editor.seleccion()))[0];
    await s.keyboard.press('p');
    for (const [x, y] of [[0.2, -0.35], [0.4, -0.4]]) await s.mouse.click(...await cli(x, y));
    await s.keyboard.press('Enter');
    await s.keyboard.down('Shift'); await s.click(`#capas li[data-id="${id1}"] .nom`); await s.keyboard.up('Shift');
    await s.keyboard.down('Meta'); await s.keyboard.press('j'); await s.keyboard.up('Meta');
    const unidos = await s.evaluate(() => window.editor.doc().capas.filter((c) => c.abierto));
    comprobar(unidos.length === 1 && unidos[0].anillos[0].length === 4, `⌘J une los dos caminos abiertos en uno de 4 nodos`);
    await s.keyboard.down('Meta'); await s.keyboard.press('j'); await s.keyboard.up('Meta');
    comprobar(!(await s.evaluate(() => window.editor.doc().capas.some((c) => c.abierto))), 'y otro ⌘J lo cierra');
    // lápiz: una onda de 120 puntos pasa a pocos nodos, abierta y con trazo
    await s.keyboard.press('Escape'); await s.keyboard.down('Shift'); await s.keyboard.press('p'); await s.keyboard.up('Shift');
    const onda = []; for (let i = 0; i <= 120; i++) onda.push(await cli(-0.4 + 0.8 * i / 120, 0.55 + 0.05 * Math.sin(i / 120 * 6)));
    await s.mouse.move(...onda[0]); await s.mouse.down(); for (const q of onda.slice(1)) await s.mouse.move(...q); await s.mouse.up();
    await s.waitForFunction(() => window.editor.doc().capas.at(-1).nombre.startsWith('Lápiz'), { timeout: 10000 });
    const lap = await s.evaluate(() => window.editor.doc().capas.at(-1));
    comprobar(lap.abierto && lap.trazo && lap.anillos[0].length <= 12, `el lápiz pasa 120 puntos a ${lap.anillos[0].length} nodos, camino abierto con trazo`);
    await s.close();
  }

  // G8: estrella y polígono paramétricos, arco de elipse, línea, flecha y texto
  {
    mkdirSync(join(e.salida, 'editor'), { recursive: true });
    writeFileSync(join(e.salida, 'editor', 'formas.json'), JSON.stringify({ version: 3, origen: null, ajustes: { fondo: 0.07, bisel: 0.008, color: [0.6, 0.05, 0.03, 1] }, capas: [] }));
    const { p: s } = await abrirEditor(e.chrome, e.url, 'formas');
    const cli = (x, y) => s.evaluate(([x, y]) => window.editor.aCliente(x, y), [x, y]);
    const ultima = () => s.evaluate(() => window.editor.doc().capas.at(-1));
    const dibujar = async (h, a, b, shift = false) => {
      await s.click(`[data-herr="${h}"]`);
      const [x0, y0] = await cli(...a), [x1, y1] = await cli(...b);
      if (shift) await s.keyboard.down('Shift');
      await s.mouse.move(x0, y0); await s.mouse.down(); await s.mouse.move(x1, y1, { steps: 4 }); await s.mouse.up();
      if (shift) await s.keyboard.up('Shift');
    };
    const campo = (k, v) => s.$eval(`[data-forma=${k}]`, (i, v) => { i.value = v; i.dispatchEvent(new Event('change', { bubbles: true })); }, v);
    const areaMundo = () => s.evaluate(() => { const c = window.editor.doc().capas.at(-1); let t = 0;
      for (const a of c.anillos) { const q = window.editor.aplanar(window.editor.redondear(a), 1e-9); let d = 0;
        for (let i = 0; i < q.length; i++) { const p = q[i], r = q[(i + 1) % q.length]; d += p[0] * r[1] - r[0] * p[1]; } t += (t ? -1 : 1) * Math.abs(d / 2); }
      return Math.abs(t * c.t.sx * c.t.sy); });  // evenodd: el primer anillo menos los huecos
    // estrella de 5 puntas, radios 0,4 y 0,16 (caja 0,8 × 0,8 e interior 0,4): N·R·r·sen(π/N)
    await dibujar('estrella', [-0.4, 0.4], [0.4, -0.4]);
    await campo('interior', '0.4');
    const est = await ultima();
    comprobar(est.forma?.tipo === 'estrella' && est.anillos[0].length === 10, 'la estrella es paramétrica: 10 nodos');
    const aE = await areaMundo(), aEx = 5 * 0.4 * 0.16 * Math.sin(Math.PI / 5);
    comprobar(Math.abs(aE - aEx) < 1e-9, `estrella de radios 0,4 y 0,16: área exacta (${aE.toFixed(9)} = ${aEx.toFixed(9)})`);
    await s.keyboard.press('Delete');
    // polígono: lados en el panel
    await dibujar('poligono', [-0.3, 0.3], [0.3, -0.3]);
    await campo('lados', '8');
    comprobar((await ultima()).anillos[0].length === 8, 'el panel cambia los lados del polígono');
    await s.keyboard.press('Enter');
    comprobar(!(await ultima()).forma, 'abrir sus nodos lo convierte en vector');
    await s.keyboard.press('Escape'); await s.keyboard.press('Delete');
    // elipse: arco de 360° con interior 50 % = el anillo (en cúbicas de 90°: ~3e-4 relativo)
    await dibujar('elipse', [-0.4, 0.4], [0.4, -0.4]);
    await campo('interior', '50');
    const el = await ultima(), aA = await areaMundo(), aAx = Math.PI * (0.16 - 0.04);
    comprobar(el.anillos.length === 2 && Math.abs(aA - aAx) / aAx < 4e-4, `elipse con interior 50 %: el anillo (área ${aA.toFixed(5)} ≈ ${aAx.toFixed(5)})`);
    await campo('barrido', '90');
    comprobar((await ultima()).anillos.length === 1 && (await ultima()).anillos[0].length === 4, 'con barrido de 90°: un cuarto de anillo (4 nodos)');
    await s.keyboard.press('Escape');
    // línea y flecha
    await dibujar('linea', [-0.4, -0.5], [0.4, -0.45], true);
    const lin = await ultima();
    comprobar(lin.abierto && lin.trazo && Math.abs(lin.anillos[0][0].p[1] - lin.anillos[0][1].p[1]) < 1e-12, 'la línea con ⇧ sale horizontal, abierta y con trazo');
    await dibujar('flecha', [-0.4, 0.55], [0.4, 0.55]);
    comprobar(await s.evaluate(() => { const g = window.editor.doc().grupos?.at(-1); return g && g.nombre.startsWith('Flecha') && window.editor.doc().capas.filter((c) => c.grupo === g.id).length === 2; }),
      'la flecha es un grupo: línea y punta');
    // texto
    await s.keyboard.press('Escape'); await s.keyboard.press('t');
    await s.mouse.click(...await cli(0, 0.7));
    await s.waitForFunction(() => !document.querySelector('#cajaTexto').hidden && document.querySelectorAll('#fuenteTexto option').length > 0, { timeout: 10000 });
    await s.type('#textoNuevo', 'Hi'); await s.keyboard.press('Enter');
    await s.waitForFunction(() => window.editor.doc().grupos?.some((g) => g.nombre === 'Texto «Hi»'), { timeout: 10000 });
    const letrasT = await s.evaluate(() => window.editor.doc().capas.filter((c) => ['H', 'i'].includes(c.nombre)).map((c) => c.anillos.flat().length));
    comprobar(letrasT.length === 2 && letrasT.every((n) => n >= 4), `el texto llega en contornos, una capa por letra (${letrasT.join(' y ')} nodos)`);
    await s.waitForFunction(() => window.editor.exacta(), { timeout: 30000 });
    comprobar(/exacta/.test(await s.$eval('#etiqueta2d', (x) => x.textContent)), 'y el servidor da la geometría exacta de todo');
    await s.close();
  }

  // G9: versión con nombre (⌥⌘S), historial con miniaturas, comparar, restaurar (y
  // deshacerlo), una copia de la versión 2 restaurada pasa por la migración, PNG 1× y 2×
  {
    const { p: s } = await abrirEditor(e.chrome, e.url, 'xi-doble');
    s.on('dialog', (d) => d.accept('Antes de mover'));
    const docTxt = () => s.evaluate(() => JSON.stringify(window.editor.doc()));
    await s.$eval('#nombre', (x) => { x.value = 'historia-ui'; });
    await s.click('#bGuardar');
    await s.waitForFunction(() => /Guardado/.test(document.querySelector('#estado').textContent), { timeout: 10000 });
    const original = await docTxt();
    await s.keyboard.down('Meta'); await s.keyboard.down('Alt'); await s.keyboard.press('KeyS'); await s.keyboard.up('Alt'); await s.keyboard.up('Meta');
    await s.waitForFunction(() => /Versión/.test(document.querySelector('#estado').textContent), { timeout: 10000 });
    await s.click('#capas li:first-child .nom');
    for (let i = 0; i < 5; i++) await s.keyboard.press('ArrowRight');
    const movido = await docTxt();
    await s.click('#bHistorial');
    await s.waitForFunction(() => document.querySelectorAll('#listaHistorial li.nombrada svg path').length > 0, { timeout: 10000 });
    comprobar(/antes de mover/.test(await s.$eval('#listaHistorial li.nombrada', (x) => x.textContent)), 'el historial lista la versión con nombre, con su miniatura');
    await s.click('#listaHistorial li.nombrada [data-hist="comparar"]');
    comprobar(await s.$$eval('#lienzo .comparar', (l) => l.length) === 2, 'comparar pinta la copia sobre el lienzo');
    await s.click('#bHistorial');
    await s.waitForFunction(() => document.querySelectorAll('#listaHistorial li.nombrada svg path').length > 0, { timeout: 10000 });
    await s.click('#listaHistorial li.nombrada [data-hist="restaurar"]');
    comprobar(await docTxt() === original, 'restaurar deja el documento idéntico a la copia');
    await s.keyboard.down('Meta'); await s.keyboard.press('z'); await s.keyboard.up('Meta');
    comprobar(await docTxt() === movido, 'y ⌘Z vuelve a lo de antes de restaurar');
    // una copia de la versión 2 (sin grupos) pasa por la migración al restaurarla
    await s.evaluate(() => window.editor.restaurar({ ...window.editor.doc(), version: 2 }));
    comprobar((await s.evaluate(() => window.editor.doc().version)) === 3, 'una copia de la versión 2 se restaura como versión 3');
    const p1 = await s.evaluate(() => window.editor.png(1, false)), p2 = await s.evaluate(() => window.editor.png(2, false));
    comprobar(p2.w === 2 * p1.w && p2.h === 2 * p1.h && p1.bytes > 1000, `el PNG a 2× mide el doble que a 1× (${p1.w}×${p1.h} → ${p2.w}×${p2.h})`);
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
      grupo: 9, anillos: [Array.from({ length: 9000 }, (_, i) => [0.4 * Math.cos(i * 2 * Math.PI / 9000), 0.4 * Math.sin(i * 2 * Math.PI / 9000)])] }],
    grupos: [{ id: 9, nombre: 'Grupo', op: 'unir' }] }));
  const { p: g } = await abrirEditor(e.chrome, e.url, 'grande');
  comprobar(await g.evaluate(() => JSON.stringify(window.editor.doc()).length) > 200 * 1024, 'el documento pasa de 200 KB, con el disco dentro de un grupo');
  await pausa(2000);  // el guardado automático de 1,5 s deja en disco la versión migrada
  await g.keyboard.down('Meta'); await g.mouse.click(...await puntoEnCapa(g)); await g.keyboard.up('Meta');  // ⌘ + clic: la capa del grupo
  await g.keyboard.press('ArrowRight', { delay: 10 });
  const xAntes = await g.evaluate(() => window.editor.doc().capas.at(-1).t.x);
  await g.close({ runBeforeUnload: true });
  // lo manda sendBeacon al cerrar: se espera a que esté en disco (con la máquina cargada,
  // 800 ms fijos no siempre bastaban)
  for (let i = 0; i < 100 && JSON.parse(readFileSync(join(e.salida, 'editor', 'grande.json'))).capas.at(-1).t.x === 0; i++) await pausa(100);
  const { p: q } = await abrirEditor(e.chrome, e.url, 'grande');
  const xDespues = await q.evaluate(() => window.editor.doc().capas.at(-1).t.x);
  comprobar(xAntes !== 0 && Math.abs(xAntes - xDespues) < 1e-12, `cerrar la pestaña sin guardar y reabrir conserva el último cambio (${xAntes} → ${xDespues})`);
} finally {
  await e.parar();
}
process.exit(resumen());
