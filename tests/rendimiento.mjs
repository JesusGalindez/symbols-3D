// Presupuesto de rendimiento del plan (docs/PLAN-EDITOR.md, regla 4): arrastrar la capa
// mayor de shou-circular a ≤ 16 ms por fotograma, mediana, sin contar el 3D.
// Se cronometra el manejador del arrastre más el estilo y la maquetación que fuerza
// (getBoundingClientRect), que es lo que el editor hace en cada movimiento del ratón.
// Uso:  npm run test:rendimiento
import { arrancar, abrirEditor, puntoEnCapa, comprobar, resumen } from './comun.mjs';

const PRESUPUESTO = 16;
const e = await arrancar(8794);
try {
  for (const simbolo of ['xi-doble', 'shou-cruz', 'shou-circular']) {
    const { p } = await abrirEditor(e.chrome, e.url, simbolo);
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
    const texto = `${simbolo.padEnd(14)} mediana ${mediana.toFixed(1)} ms · p90 ${p90.toFixed(1)} ms`;
    if (simbolo === 'shou-circular') comprobar(mediana <= PRESUPUESTO, `${texto} (presupuesto ${PRESUPUESTO} ms)`);
    else console.log(`       ${texto}`);
    await p.close();
  }
} finally {
  await e.parar();
}
process.exit(resumen());
