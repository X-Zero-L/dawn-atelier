import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const CONFIG = JSON.parse(await fs.readFile(path.join(ROOT, 'scripts/media-config.json'), 'utf8'));
export const sha256 = data => createHash('sha256').update(data).digest('hex');
export const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd || ROOT,
      env: {...process.env, ...options.env},
      windowsHide: true,
      stdio: options.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
      shell: process.platform === 'win32' && command === 'npm',
    });
    let stdout = '', stderr = '';
    if (options.capture) {
      child.stdout.on('data', data => stdout += data);
      child.stderr.on('data', data => stderr += data);
    }
    child.on('error', reject);
    child.on('close', code => {
      if (code === 0) resolve(stdout.trim());
      else reject(new Error(`${command} exited with ${code}${stderr ? ': ' + stderr.trim() : ''}`));
    });
  });
}

async function artworkSnapshot() {
  let local = {};
  try { local = JSON.parse((await fs.readFile(path.join(ROOT, 'config.local.json'), 'utf8')).replace(/^\uFEFF/, '')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const configured = process.env.DAWN_ASSET_DIR || local.asset_dir || 'web/assets';
  const directory = path.resolve(ROOT, configured.replace(/^~(?=[\\/]|$)/, os.homedir()));
  const files = [];
  async function walk(relative = '') {
    let entries;
    try { entries = await fs.readdir(path.join(directory, relative), {withFileTypes: true}); }
    catch (error) { if (error.code === 'ENOENT') return; throw error; }
    for (const entry of entries) {
      const name = path.posix.join(relative, entry.name);
      if (entry.isDirectory()) await walk(name);
      else if (entry.isFile() && /\.(?:svg|webp|png|jpe?g|gif|avif|ico)$/i.test(name)) {
        files.push([name, sha256(await fs.readFile(path.join(directory, name)))]);
      }
    }
  }
  await walk();
  files.sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0);
  return {fingerprint: sha256(JSON.stringify(files)), files};
}

export async function sourceSnapshot() {
  const listed = await run('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], {capture: true});
  const files = [...new Set(listed.split('\0').filter(Boolean))].filter(file =>
    /^(?:web\/(?:[^/]+\.(?:js|css|html)|brand\/)|desktop\/|schemas\/|scripts\/|video\/(?:src\/|scripts\/|package(?:-lock)?\.json))/.test(file)
      || /^[^/]+\.pyw?$/.test(file) || file === 'version.json' || file === 'requirements.txt' || file === '.github/workflows/refresh-media.yml',
  ).sort();
  const hashes = [];
  for (const file of files) {
    const bytes = await fs.readFile(path.join(ROOT, file));
    hashes.push([file, sha256(bytes)]);
  }
  const [changed, untracked, artwork] = await Promise.all([
    run('git', ['diff', '--name-only', 'HEAD', '-z'], {capture: true}),
    run('git', ['ls-files', '--others', '--exclude-standard', '-z'], {capture: true}),
    artworkSnapshot(),
  ]);
  return {
    commit: await run('git', ['rev-parse', 'HEAD'], {capture: true}),
    dirty: [...changed.split('\0'), ...untracked.split('\0')].some(file => files.includes(file)),
    fingerprint: sha256(JSON.stringify({files: hashes, artwork: artwork.fingerprint})),
    files: hashes,
    artwork,
  };
}

export async function describeFile(file) {
  const bytes = await fs.readFile(file);
  return {bytes: bytes.length, sha256: sha256(bytes)};
}

export async function removeOwnedTemporaryDirectory(directory, parent, prefix) {
  const resolved = path.resolve(directory);
  if (path.dirname(resolved) !== path.resolve(parent) || !path.basename(resolved).startsWith(prefix)) {
    throw new Error('Refusing to remove a temporary directory outside the media workspace.');
  }
  await fs.rm(resolved, {recursive: true, force: true, maxRetries: 5, retryDelay: 300});
}
