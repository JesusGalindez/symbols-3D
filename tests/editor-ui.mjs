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
    const fin = await s.evaluate((id) => { const c = window.editor.doc().capas.find((k) => k.id === id), [u, v] = c.anillos[0][0];
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
    // puntos de cada capa en el mundo, y el centro de su caja
    const mundo = () => s.evaluate(() => window.editor.doc().capas.map((c) => c.anillos.flatMap((r) => r.map(([u, v]) => {
      const co = Math.cos(c.t.r), si = Math.sin(c.t.r);
      return [c.t.x + co * u * c.t.sx - si * v * c.t.sy, c.t.y + si * u * c.t.sx + co * v * c.t.sy]; }))));
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
    const P0 = await mundo(), W0 = Number(await s.$eval('[data-q=w]', (i) => i.value));
    const todos0 = P0.flat(), O = (Math.min(...todos0.map((q) => q[0])) + Math.max(...todos0.map((q) => q[0]))) / 2;
    await s.$eval('[data-q=w]', (i, v) => { i.value = v; i.dispatchEvent(new Event('change', { bubbles: true })); }, String(W0 * 1.5));
    const P1 = await mundo();
    // W0 sale del panel con 3 decimales: la escala real es el ancho pedido entre el exacto
    const Wexacto = Math.max(...todos0.map((q) => q[0])) - Math.min(...todos0.map((q) => q[0])), kr = (W0 * 1.5) / Wexacto;
    let err = 0;
    P0.forEach((P, i) => P.forEach((q, j) => { err = Math.max(err, Math.abs(P1[i][j][0] - (O + kr * (q[0] - O))), Math.abs(P1[i][j][1] - q[1])); }));
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
