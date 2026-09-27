import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';

const project = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const config = JSON.parse(await readFile(path.join(project, '../scripts/media-config.json'), 'utf8'));
const args = process.argv.slice(2);
if (args.includes('--draft')) throw new Error('Draft asset fallbacks have been removed. Provide current named screenshots using --source <directory>.');
const sourceArg = args.indexOf('--source');
const source = sourceArg >= 0 ? path.resolve(args[sourceArg + 1]) : path.resolve(project, '../docs/images');
const names = config.screenshots;
if (!Array.isArray(names) || new Set(names).size !== names.length || names.some(name => !/^[a-z][a-z0-9-]*$/.test(name))) throw new Error('Invalid screenshot names in scripts/media-config.json.');
if (!names.includes('desktop') || !names.includes('desktop-preparing')) throw new Error('Desktop showcase screenshots are required.');
const target = path.join(project, 'public');
const inputs = await Promise.all(names.map(async (name) => {
  const filename = `${name}.png`;
  const data = await readFile(path.join(source, filename));
  if (data.length < 24 || data.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') throw new Error(`Not a PNG: ${filename}`);
  return {name, filename, data, width: data.readUInt32BE(16), height: data.readUInt32BE(20), sha256: createHash('sha256').update(data).digest('hex')};
}));
const font = JSON.parse(await readFile(path.join(project, 'src/fonts/font.json'), 'utf8'));
const fontBytes = await readFile(path.join(project, 'src/fonts', font.file));
if (createHash('sha256').update(fontBytes).digest('hex') !== font.sha256) throw new Error('Bundled font differs from its provenance hash.');
await mkdir(target, {recursive: true});
const manifest = {mode: 'release', screenshots: {}};
for (const {name, filename, data, width, height, sha256} of inputs) {
  await writeFile(path.join(target, `${name}.png`), data);
  manifest.screenshots[name] = {file: filename, width, height, sha256};
}
await writeFile(path.join(target, 'assets.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Prepared ${names.length} ${manifest.mode} screenshots in video/public/.`);
