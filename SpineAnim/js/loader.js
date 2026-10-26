const ATLAS_NAME = /\.atlas(\.txt)?$/i;
const JSON_NAME = /\.json$/i;
const SKEL_NAME = /\.skel$/i;
const IMAGE_NAME = /\.(png|jpe?g|webp)$/i;

function baseName(path) {
  return path.split('/').pop();
}

function stemOf(name) {
  return baseName(name).replace(/\.[^.]+$/, '');
}

function dirOf(file) {
  const path = file.webkitRelativePath || file.name;
  const parts = path.split('/');
  parts.pop();
  return parts.join('/');
}

function sortFiles(fileList) {
  const files = Array.from(fileList);
  return {
    json: files.filter((f) => JSON_NAME.test(f.name)),
    skel: files.filter((f) => SKEL_NAME.test(f.name)),
    atlas: files.filter((f) => ATLAS_NAME.test(f.name)),
    image: files.filter((f) => IMAGE_NAME.test(f.name)),
  };
}

function pickAtlas(jsonFile, atlases) {
  const stem = stemOf(jsonFile.name);
  const dir = dirOf(jsonFile);
  const neighbours = atlases.filter((a) => dirOf(a) === dir);
  const pool = neighbours.length ? neighbours : atlases;
  return pool.find((a) => stemOf(a.name) === stem)
    || pool.find((a) => stem.startsWith(stemOf(a.name)) || stemOf(a.name).startsWith(stem))
    || pool[0] || null;
}

function pickImage(pageName, images) {
  const base = baseName(pageName).toLowerCase();
  return images.find((f) => f.name.toLowerCase() === pageName.toLowerCase())
    || images.find((f) => f.name.toLowerCase() === base)
    || images.find((f) => baseName(f.name).toLowerCase() === base)
    || (images.length === 1 ? images[0] : null);
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('贴图读不出来：' + file.name));
    img.src = url;
  });
}

function looksStraightAlpha(image) {
  const size = 256;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(image, 0, 0, size, size);
  const data = ctx.getImageData(0, 0, size, size).data;
  let semi = 0;
  let straight = 0;
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3];
    if (a === 0 || a === 255) continue;
    semi += 1;
    if (Math.max(data[i], data[i + 1], data[i + 2]) > a + 2) straight += 1;
  }
  return semi > 40 && straight > semi * 0.2;
}

async function buildSpineAsset(bundle, gl, options) {
  const jsonFile = bundle.json.find((f) => f.name === options.jsonName) || bundle.json[0];
  const atlasFile = pickAtlas(jsonFile, bundle.atlas);
  if (!atlasFile) throw new Error('同目录下没有找到 .atlas');
  const atlasText = await atlasFile.text();
  const atlas = new spine.TextureAtlas(atlasText);
  const pages = [];
  let premultiplied = true;
  for (const page of atlas.pages) {
    const file = pickImage(page.name, bundle.image);
    if (!file) throw new Error('缺少图集里的贴图：' + page.name);
    const image = await loadImage(file);
    const straight = options.pma === 'auto' ? looksStraightAlpha(image) : options.pma === 'straight';
    premultiplied = !straight;
    page.setTexture(new spine.GLTexture(gl, image, premultiplied));
    pages.push({ name: page.name, width: image.width, height: image.height, straight, file: file.name });
  }
  const attachmentLoader = new spine.AtlasAttachmentLoader(atlas);
  let data;
  if (SKEL_NAME.test(jsonFile.name)) {
    data = new spine.SkeletonBinary(attachmentLoader).readSkeletonData(new Uint8Array(await jsonFile.arrayBuffer()));
  } else {
    data = new spine.SkeletonJson(attachmentLoader).readSkeletonData(await jsonFile.text());
  }
  return { data, atlas, pages, premultiplied, jsonFile, atlasFile };
}

function defaultSkinNames(data) {
  const names = data.skins.map((s) => s.name).filter((n) => n !== 'default');
  const full = names.filter((n) => n.startsWith('full-skins/'));
  if (full.length) return [full[0]];
  const base = names.filter((n) => n === 'skin-base');
  return base.length ? base : [];
}

function combinedSkin(data, names) {
  if (!names.length) return null;
  if (names.length === 1) return data.findSkin(names[0]);
  const skin = new spine.Skin('preview');
  for (const name of names) {
    const part = data.findSkin(name);
    if (part) skin.addSkin(part);
  }
  return skin;
}
