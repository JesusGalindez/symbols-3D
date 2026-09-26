// Común a las pruebas de Chrome: un servidor del editor propio, con toda la salida en
// una carpeta temporal (nada cae en glb/, svg/ ni editor/), y un Chrome sin ventana.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

export async function arrancar(puerto = 8793) {
  const salida = mkdtempSync(join(tmpdir(), 'editor-prueba-'));
  const servidor = spawn(join(RAIZ, '.venv/bin/python'),
    [join(RAIZ, 'tools/editor.py'), '--puerto', String(puerto), '--salida', salida], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((ok, mal) => {
    servidor.stdout.on('data', (d) => String(d).includes('Editor en') && ok());
    servidor.on('exit', (c) => mal(new Error(`el servidor salió con código ${c}`)));
  });
  // SwiftShader: WebGL por software, igual en cualquier Mac y sin ventana
  const chrome = await puppeteer.launch({ executablePath: CHROME, headless: 'new',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'], defaultViewport: { width: 1500, height: 850 } });
  return {
    url: `http://localhost:${puerto}/editor.html`, salida, chrome,
    async parar() { await chrome.close(); servidor.kill(); rmSync(salida, { recursive: true, force: true }); },
  };
}

// abre el editor y espera a que llegue la geometría exacta del servidor
export async function abrirEditor(chrome, url, simbolo) {
  const p = await chrome.newPage();
  const errores = [];
  p.on('pageerror', (e) => errores.push(e.message));
  p.on('requestfailed', (r) => errores.push(`sin cargar: ${r.url()}`));
  // como sin internet: todo lo que no sea el servidor local se corta y cuenta como error
  await p.setRequestInterception(true);
  p.on('request', (r) => (new URL(r.url()).hostname === 'localhost' ? r.continue() : r.abort()));
  await p.goto(`${url}?s=${simbolo}`, { waitUntil: 'networkidle0' });
  await p.waitForFunction(() => window.editor?.exacta(), { timeout: 30000 });
  return { p, errores };
}

// un punto de la pantalla que cae dentro de la capa (el primero que encuentra)
export function puntoEnCapa(p, id) {
  return p.evaluate((id) => {
    const el = document.querySelector(id ? `#lienzo path.capa[data-id="${id}"]` : '#lienzo path.capa');
    const r = el.getBoundingClientRect();
    for (let y = r.top + 2; y < r.bottom; y += 3) for (let x = r.left + 2; x < r.right; x += 3)
      if (document.elementFromPoint(x, y) === el) return [x, y];
    return null;
  }, id);
}

let fallos = 0;
export function comprobar(cond, texto) {
  console.log(`${cond ? 'PASA ' : 'FALLA'}  ${texto}`);
  if (!cond) fallos++;
}
export const resumen = () => { console.log(fallos ? `\n${fallos} fallo(s)` : '\ntodo en verde'); return fallos ? 1 : 0; };
