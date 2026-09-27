import {copyFile, mkdir, readFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';

const project = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const args = process.argv.slice(2);
const draft = args.includes('--draft');
const sourceArg = args.indexOf('--source');
const source = sourceArg >= 0 ? path.resolve(args[sourceArg + 1]) : path.resolve(project, '../docs/images');
const names = ['overview', 'presets', 'inventory', 'relationships', 'tools', 'preview', 'mobile'];
const temporary = ['home-presets', 'presets-desktop', 'focused-inventory', 'focused-favor', 'focused-tools', 'preset-review', 'presets-mobile'];
const target = path.join(project, 'public');
await mkdir(target, {recursive: true});
const manifest = {mode: draft ? 'draft' : 'release', screenshots: {}};
for (const [index, name] of names.entries()) {
  const filename = `${draft ? temporary[index] : name}.png`;
  const data = await readFile(path.join(source, filename));
  await copyFile(path.join(source, filename), path.join(target, `${name}.png`));
  manifest.screenshots[name] = {file: filename, sha256: createHash('sha256').update(data).digest('hex')};
}
await writeFile(path.join(target, 'assets.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(`Prepared ${names.length} ${manifest.mode} screenshots in video/public/.`);
