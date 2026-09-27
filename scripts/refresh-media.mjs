import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {CONFIG, ROOT, delay, describeFile, run, sha256, sourceSnapshot, removeOwnedTemporaryDirectory} from './media-lib.mjs';

const args = process.argv.slice(2);
const options = {publish: false, publishOnly: false, commit: false, release: 'latest'};
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--publish') options.publish = true;
  else if (args[i] === '--publish-only') options.publish = options.publishOnly = true;
  else if (args[i] === '--commit') options.commit = true;
  else if (args[i] === '--release' && args[i + 1]) options.release = args[++i];
  else if (args[i] === '--help') {
    console.log('node scripts/refresh-media.mjs [--publish | --publish-only] [--release latest|TAG] [--commit]\n\nDefault: capture all screenshots, render MP4/poster/GIF and record hashes.\n--publish: also replace media on the selected existing release.\n--publish-only: publish existing outputs only after a source/hash freshness check.\n--commit: commit only generated gallery/README files, then push the current branch.\nSource changes must be committed before --publish or --commit.');
    process.exit(0);
  } else throw new Error('Unknown or incomplete option: ' + args[i]);
}
if (!/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(options.release)) throw new Error('Invalid release tag.');
const video = path.join(ROOT, 'video');
const out = path.join(video, 'out');
const gallery = path.join(ROOT, 'docs/images');
const manifestFile = path.join(out, 'media-manifest.json');
const generated = [
  ...CONFIG.screenshots.map(name => `docs/images/${name}.png`),
  'docs/images/screenshots.json', 'docs/images/video-poster.png', 'docs/images/demo.gif',
  'docs/media-manifest.json', 'README.md',
];
const concurrency = process.env.DAWN_RENDER_CONCURRENCY || '2';
if (!/^(?:[1-9]|1[0-6])$/.test(concurrency)) throw new Error('DAWN_RENDER_CONCURRENCY must be 1–16.');

async function readJson(file) { return JSON.parse(await fs.readFile(file, 'utf8')); }
async function writeJson(file, value) { await fs.writeFile(file, JSON.stringify(value, null, 2) + '\n'); }
async function exists(file) { try { await fs.access(file); return true; } catch { return false; } }
function updateVideoLinks(readme) {
  return readme.replace(/https:\/\/github\.com\/X-Zero-L\/dawn-atelier\/releases\/(?:download\/[^/]+|latest\/download)\/dawn-atelier-demo\.mp4/g,
    `https://github.com/${CONFIG.repository}/releases/latest/download/dawn-atelier-demo.mp4`);
}

async function requireCommittedSource() {
  if (!options.commit && !options.publish) return;
  if (await run('git', ['diff', '--cached', '--name-only'], {capture: true})) throw new Error('Commit or unstage existing staged changes first.');
  const changed = await run('git', ['diff', '--name-only', '-z'], {capture: true});
  const untracked = await run('git', ['ls-files', '--others', '--exclude-standard', '-z'], {capture: true});
  const other = [...changed.split('\0'), ...untracked.split('\0')].filter(file => file && !generated.includes(file));
  if (other.length) throw new Error('Commit source changes before publication or automatic commit:\n' + other.join('\n'));
  if (changed.split('\0').includes('README.md')) {
    const committed = await run('git', ['show', 'HEAD:README.md'], {capture: true});
    const current = (await fs.readFile(path.join(ROOT, 'README.md'), 'utf8')).replaceAll('\r\n', '\n').trim();
    if (current !== updateVideoLinks(committed).replaceAll('\r\n', '\n').trim()) throw new Error('Commit unrelated README edits before automatic publication. Only generated video-link edits are allowed.');
  }
}

async function pythonCommand() {
  if (process.env.DAWN_PYTHON) return process.env.DAWN_PYTHON;
  const local = path.join(ROOT, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  return await exists(local) ? local : process.platform === 'win32' ? 'python' : 'python3';
}

async function captureScreenshots() {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'dawn-atelier-media-'));
  const staging = path.join(temporary, 'screenshots');
  const python = await pythonCommand();
  let server, serverError, serverText = '', serverLog = '';
  try {
    console.log(`1/5 Starting a fresh synthetic demo and capturing all ${CONFIG.screenshots.length} views…`);
    const bootstrap = 'import web_server; s=web_server.ThreadingHTTPServer(("127.0.0.1",0),web_server.Handler); print("DAWN_MEDIA_PORT="+str(s.server_port),flush=True); s.serve_forever()';
    server = spawn(python, ['-X', 'utf8', '-u', '-c', bootstrap], {
      cwd: ROOT, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
      env: {...process.env, DAWN_DEMO: '1', DAWN_DATA_DIR: path.join(temporary, 'data'), PYTHONUNBUFFERED: '1'},
    });
    server.on('error', error => { serverError = error; });
    server.stdout.on('data', data => { serverText += data; });
    server.stderr.on('data', data => { serverLog += data; });
    let port;
    for (let i = 0; i < 200; i++) {
      if (serverError || server.exitCode !== null) throw new Error('Demo startup failed: ' + (serverError?.message || serverLog));
      port = /DAWN_MEDIA_PORT=(\d+)/.exec(serverText)?.[1];
      if (port) break;
      await delay(100);
    }
    if (!port) throw new Error('Demo did not start within 20 seconds. ' + serverLog);
    await run(process.execPath, [path.join(ROOT, 'scripts/capture-demo.mjs')], {
      env: {DAWN_DEMO_URL: `http://127.0.0.1:${port}`, DAWN_CAPTURE_DIR: staging},
    });
    const capture = await readJson(path.join(staging, 'screenshots.json'));
    if (!capture.syntheticDemo || CONFIG.screenshots.some(name => !capture.screenshots[name])) throw new Error('Capture did not produce the complete demo gallery.');
    await fs.mkdir(gallery, {recursive: true});
    for (const name of CONFIG.screenshots) await fs.copyFile(path.join(staging, name + '.png'), path.join(gallery, name + '.png'));
    await fs.copyFile(path.join(staging, 'screenshots.json'), path.join(gallery, 'screenshots.json'));
    return capture;
  } finally {
    if (server && server.exitCode === null) {
      server.kill();
      for (let i = 0; i < 50 && server.exitCode === null && !server.signalCode; i++) await delay(100);
    }
    await fs.writeFile(path.join(out, 'demo-server.log'), serverLog);
    await removeOwnedTemporaryDirectory(temporary, os.tmpdir(), 'dawn-atelier-media-');
  }
}

async function render() {
  const snapshot = await sourceSnapshot();
  await run('ffmpeg', ['-version'], {capture: true});
  await run('ffprobe', ['-version'], {capture: true});
  const capture = await captureScreenshots();
  if (capture.source.fingerprint !== snapshot.fingerprint) throw new Error('Source changed before capture completed. Run again.');
  console.log('2/5 Preparing locked video dependencies and fresh screenshot inputs…');
  const cli = path.join(video, 'node_modules/@remotion/cli/remotion-cli.js');
  const dependencyHash = sha256(Buffer.concat([
    await fs.readFile(path.join(video, 'package.json')),
    await fs.readFile(path.join(video, 'package-lock.json')),
  ]));
  const dependencyMarker = path.join(video, 'node_modules/.dawn-media-lock');
  if (!await exists(cli) || !await exists(dependencyMarker) || (await fs.readFile(dependencyMarker, 'utf8')).trim() !== dependencyHash) {
    await run('npm', ['ci', '--no-audit', '--no-fund'], {cwd: video});
    await fs.writeFile(dependencyMarker, dependencyHash + '\n');
  }
  await run(process.execPath, [path.join(video, 'scripts/prepare-assets.mjs')]);
  const inputs = await readJson(path.join(video, 'public/assets.json'));
  for (const name of CONFIG.screenshots) {
    if (inputs.screenshots[name]?.sha256 !== capture.screenshots[name].sha256) throw new Error('Stale video input: ' + name);
  }
  const timeline = await readJson(path.join(video, 'src/timeline.json'));
  const duration = timeline.durationInFrames / timeline.fps;
  const mp4 = path.join(out, 'dawn-atelier-demo.mp4');
  const poster = path.join(out, 'dawn-atelier-poster.png');
  const gif = path.join(out, 'dawn-atelier-demo.gif');
  console.log(`3/5 Rendering ${duration} seconds at ${timeline.width} × ${timeline.height}, ${timeline.fps} fps…`);
  await fs.writeFile(path.join(out, 'render.log'), await run(process.execPath, [cli, 'render', 'src/index.jsx', timeline.id, mp4,
    '--codec=h264', '--crf=18', '--pixel-format=yuv420p', `--concurrency=${concurrency}`], {cwd: video, capture: true}));
  await fs.writeFile(path.join(out, 'poster.log'), await run(process.execPath, [cli, 'still', 'src/index.jsx', timeline.id, poster,
    `--frame=${timeline.posterFrame}`], {cwd: video, capture: true}));
  console.log('4/5 Building GIF, frame samples and the contact sheet…');
  const gifFilter = '[0:v]setpts=PTS/2,fps=8,scale=720:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3';
  await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', mp4, '-filter_complex', gifFilter, '-loop', '0', gif]);
  const samples = Object.entries(timeline.sampleFrames);
  const select = samples.map(([, frame]) => `eq(n\\,${frame})`).join('+');
  await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', mp4, '-vf',
    `select=${select},scale=640:360,tile=3x${Math.ceil(samples.length / 3)}:padding=12:margin=12:color=0xf6f3e9`,
    '-frames:v', '1', path.join(out, 'contact-sheet.png')]);
  for (const [name, frame] of samples) {
    await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-ss', String(frame / timeline.fps), '-i', mp4,
      '-frames:v', '1', path.join(out, 'frame-' + name + '.png')]);
  }
  const probe = JSON.parse(await run('ffprobe', ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', mp4], {capture: true}));
  const stream = probe.streams.find(value => value.codec_type === 'video');
  if (!stream || stream.width !== timeline.width || stream.height !== timeline.height || Number(stream.nb_frames) !== timeline.durationInFrames
      || stream.r_frame_rate !== `${timeline.fps}/1` || Math.abs(Number(probe.format.duration) - duration) > 0.1
      || probe.streams.some(value => value.codec_type === 'audio')) throw new Error('Rendered video does not match the timeline.');
  if ((await sourceSnapshot()).fingerprint !== snapshot.fingerprint) throw new Error('Source changed while rendering. Run again before publication.');
  await fs.copyFile(poster, path.join(gallery, 'video-poster.png'));
  await fs.copyFile(gif, path.join(gallery, 'demo.gif'));
  const files = {};
  for (const name of CONFIG.mediaFiles) files[name] = await describeFile(path.join(out, name));
  const manifest = {
    schemaVersion: 1, generatedAt: new Date().toISOString(), gameTitle: CONFIG.gameTitle,
    source: snapshot, screenshots: capture.screenshots,
    video: {width: stream.width, height: stream.height, fps: timeline.fps, frames: timeline.durationInFrames, duration, codec: stream.codec_name, audio: false},
    files,
  };
  await writeJson(manifestFile, manifest);
  await writeJson(path.join(ROOT, 'docs/media-manifest.json'), manifest);
  await fs.writeFile(path.join(out, 'SHA256SUMS'), Object.entries({...files, 'media-manifest.json': await describeFile(manifestFile)})
    .map(([name, info]) => `${info.sha256}  ${name}`).join('\n') + '\n');
  const readmeFile = path.join(ROOT, 'README.md');
  const readme = await fs.readFile(readmeFile, 'utf8');
  await fs.writeFile(readmeFile, updateVideoLinks(readme));
}

async function verifyFreshness() {
  const manifest = await readJson(manifestFile);
  if (options.publish && manifest.source.dirty) throw new Error('These media were rendered from uncommitted source. Commit the source and regenerate before publishing.');
  if (manifest.source.fingerprint !== (await sourceSnapshot()).fingerprint) throw new Error('Media is older than the current source. Regenerate it first.');
  const capture = await readJson(path.join(gallery, 'screenshots.json'));
  if (capture.source.fingerprint !== manifest.source.fingerprint) throw new Error('Screenshot provenance differs from the video.');
  for (const name of CONFIG.screenshots) {
    const current = await describeFile(path.join(gallery, name + '.png'));
    if (current.sha256 !== manifest.screenshots[name]?.sha256 || current.sha256 !== capture.screenshots[name]?.sha256) throw new Error('Screenshot changed after rendering: ' + name);
  }
  for (const name of CONFIG.mediaFiles) {
    if ((await describeFile(path.join(out, name))).sha256 !== manifest.files[name]?.sha256) throw new Error('Media changed after rendering: ' + name);
  }
  for (const [name, outputName] of [['demo.gif', 'dawn-atelier-demo.gif'], ['video-poster.png', 'dawn-atelier-poster.png']]) {
    if ((await describeFile(path.join(gallery, name))).sha256 !== manifest.files[outputName].sha256) throw new Error('README preview differs from release output: ' + name);
  }
  if ((await describeFile(path.join(ROOT, 'docs/media-manifest.json'))).sha256 !== (await describeFile(manifestFile)).sha256) throw new Error('Gallery media manifest differs from output.');
  const expectedSums = Object.entries({...manifest.files, 'media-manifest.json': await describeFile(manifestFile)})
    .map(([name, info]) => `${info.sha256}  ${name}`).join('\n') + '\n';
  if (await fs.readFile(path.join(out, 'SHA256SUMS'), 'utf8') !== expectedSums) throw new Error('Checksum file differs from outputs.');
  return manifest;
}

async function commitMedia() {
  await requireCommittedSource();
  const changed = await run('git', ['diff', '--name-only', '-z'], {capture: true});
  const untracked = await run('git', ['ls-files', '--others', '--exclude-standard', '-z'], {capture: true});
  const files = [...new Set([...changed.split('\0'), ...untracked.split('\0')])].filter(file => generated.includes(file));
  if (files.length) {
    const message = path.join(out, 'media-commit.txt');
    await fs.writeFile(message, 'docs: keep player previews aligned with the current workbench\n\nConstraint: Public captures use synthetic demo saves.\nConfidence: high\nScope-risk: narrow\nTested: Complete gallery capture, media hashes and video metadata.\nNot-tested: Gameplay effects were not evaluated.\n');
    await run('git', ['add', '--', ...files]);
    await run('git', ['commit', '--file=' + message]);
  }
  const branch = await run('git', ['branch', '--show-current'], {capture: true});
  if (!branch) throw new Error('Automatic push requires a branch, not detached HEAD.');
  await run('git', ['-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', 'push', 'origin', branch]);
}

async function publish() {
  const release = JSON.parse(await run('gh', ['release', 'view', ...(options.release === 'latest' ? [] : [options.release]),
    '--repo', CONFIG.repository, '--json', 'tagName,body,url'], {capture: true}));
  console.log('5/5 Updating media on ' + release.tagName + '…');
  const attachments = [...CONFIG.mediaFiles, 'media-manifest.json', 'SHA256SUMS'];
  await run('gh', ['release', 'upload', release.tagName, ...attachments.map(name => path.join(out, name)), '--repo', CONFIG.repository, '--clobber']);
  const demoUrl = `https://github.com/${CONFIG.repository}/releases/download/${encodeURIComponent(release.tagName)}/dawn-atelier-demo.mp4`;
  const section = `<!-- dawn-media:start -->\n## 操作演示\n\n[观看《${CONFIG.gameTitle}》工坊演示](${demoUrl})：超级补给、炼金沉淀物、背包整理与保存前预览。\n<!-- dawn-media:end -->`;
  const marker = /<!-- dawn-media:start -->[\s\S]*?<!-- dawn-media:end -->/;
  const notes = marker.test(release.body) ? release.body.replace(marker, section) : release.body.trimEnd() + '\n\n' + section + '\n';
  const notesFile = path.join(out, 'release-notes.md');
  await fs.writeFile(notesFile, notes);
  await run('gh', ['release', 'edit', release.tagName, '--repo', CONFIG.repository, '--notes-file', notesFile]);
  const remote = JSON.parse(await run('gh', ['release', 'view', release.tagName, '--repo', CONFIG.repository, '--json', 'assets'], {capture: true}));
  for (const name of attachments) {
    const asset = remote.assets.find(value => value.name === name);
    const local = await describeFile(path.join(out, name));
    if (!asset || asset.size !== local.bytes || (asset.digest && asset.digest !== 'sha256:' + local.sha256)) throw new Error('Uploaded asset differs: ' + name);
  }
  console.log('Published: ' + release.url);
}

await fs.mkdir(out, {recursive: true});
await requireCommittedSource();
if (!options.publishOnly) {
  // A failed run must not leave a usable marker for an older render.
  await fs.rm(manifestFile, {force: true});
  await render();
}
const manifest = await verifyFreshness();
if (options.commit) await commitMedia();
if (options.publish) await publish();
console.log(`Complete: ${CONFIG.screenshots.length} screenshots, ${manifest.video.duration}s MP4, GIF and poster.\nOutputs: ${out}\nSource fingerprint: ${manifest.source.fingerprint}`);
