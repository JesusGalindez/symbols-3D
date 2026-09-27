// Presupuesto de rendimiento del plan (docs/PLAN-EDITOR.md, regla 4): arrastrar la capa
// mayor de shou-circular a ≤ 16 ms por fotograma, mediana, sin contar el 3D.
// Se cronometra el manejador del arrastre más el estilo y la maquetación que fuerza
// (getBoundingClientRect), que es lo que el editor hace en cada movimiento del ratón.
// Uso:  npm run test:rendimiento
import { arrancar, abrirEditor, puntoEnCapa, comprobar, resumen } from './comun.mjs';

const PRESUPUESTO = 16;
const e = await arrancar(8794);
try {
  // el último: shou-circular con un rectángulo que interseca encima (G4): la vista
  // provisional recorta lo de debajo con un clipPath
  for (const simbolo of ['xi-doble', 'shou-cruz', 'shou-circular', 'shou-circular+intersecar']) {
    const { p } = await abrirEditor(e.chrome, e.url, simbolo.split('+')[0]);
    if (simbolo.endsWith('+intersecar')) {
      const [a, b] = await p.evaluate(() => [window.editor.aCliente(0, 0.6), window.editor.aCliente(0.6, -0.6)]);
      await p.keyboard.press('r');
      await p.mouse.move(...a); await p.mouse.down(); await p.mouse.move(...b, { steps: 4 }); await p.mouse.up();
      await p.select('[data-p=op]', 'intersecar');
      await p.keyboard.press('Escape');
      await p.waitForFunction(() => window.editor.exacta(), { timeout: 60000 });
    }
    const pto = await puntoEnCapa(p);
    const { mediana, p90 } = await p.evaluate(([x, y]) => {
      const el = document.elementFromPoint(x, y);
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: x, clientY: y, button: 0 }));
      const t = [];
      for (let i = 1; i <= 40; i++) {
        const t0 = performance.now();
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: x + i * 2, clientY: y }));
        document.querySelector('#lienzo').getBoundingClientRect();
        t.push(performance.now() - t0);
      }
      window.dispatchEvent(new PointerEvent('pointerup', {}));
      t.sort((a, b) => a - b);
      return { mediana: t[20], p90: t[36] };
    }, pto);
    const texto = `${simbolo.padEnd(25)} mediana ${mediana.toFixed(1)} ms · p90 ${p90.toFixed(1)} ms`;
    if (simbolo.startsWith('shou-circular')) comprobar(mediana <= PRESUPUESTO, `${texto} (presupuesto ${PRESUPUESTO} ms)`);
    else console.log(`       ${texto}`);
    await p.close();
  }
  // G7: mover 50 nodos elegidos a la vez en la capa mayor de shou-circular
  {
    const { p } = await abrirEditor(e.chrome, e.url, 'shou-circular');
    await p.click('#capas li:last-child .nom'); await p.keyboard.press('Enter');
    await p.evaluate(() => window.editor.elegirNodos(50));
    const nodo = await p.$eval('#sobre .nodo.sel', (x) => { const r = x.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
    const { mediana, p90 } = await p.evaluate(([x, y]) => {
      const el = document.elementFromPoint(x, y);
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: x, clientY: y, button: 0 }));
      const t = [];
      for (let i = 1; i <= 40; i++) {
        const t0 = performance.now();
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: x + i * 2, clientY: y }));
        document.querySelector('#lienzo').getBoundingClientRect();
        t.push(performance.now() - t0);
      }
      window.dispatchEvent(new PointerEvent('pointerup', {}));
      t.sort((a, b) => a - b);
      return { mediana: t[20], p90: t[36] };
    }, nodo);
    comprobar(mediana <= PRESUPUESTO, `shou-circular, 50 nodos    mediana ${mediana.toFixed(1)} ms · p90 ${p90.toFixed(1)} ms (presupuesto ${PRESUPUESTO} ms)`);
    await p.close();
  }
} finally {
  await e.parar();
}
process.exit(resumen());
