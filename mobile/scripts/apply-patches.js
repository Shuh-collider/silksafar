#!/usr/bin/env node
/**
 * Восстанавливает наши правки внутри node_modules после `npm install`.
 *
 * Зачем это вообще существует. У пакета react-native-mlkit-translate в npm
 * лежит android/build.gradle времён AGP 3.4.1: jcenter, плагин 'maven',
 * compileSdk 28, зависимость 'com.facebook.react:react-native:+'. С Gradle 8
 * он не собирается — сборка падает на «Plugin with id 'maven' not found».
 * Файл был переписан вручную, и эта правка ЖИЛА ТОЛЬКО ВНУТРИ node_modules:
 * ни в замке, ни в репозитории её не было. Обнаружилось это 30.07.2026, когда
 * пересоздавали package-lock.json — папку удалили, и сборка сломалась.
 *
 * Теперь правленые файлы лежат в mobile/patches/, а этот скрипт запускается
 * автоматически через postinstall. Версия пакета проверяется: если она
 * изменилась, патч НЕ применяется — вместо этого печатается предупреждение,
 * потому что накладывать старый патч на новый пакет опаснее, чем не наложить.
 *
 * Если понадобится что-то ещё пропатчить — создайте
 * patches/<имя-пакета>@<версия>/<путь внутри пакета> и всё.
 */

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const patchesDir = path.join(root, 'patches');
const modulesDir = path.join(root, 'node_modules');

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

function installedVersion(pkgName) {
  try {
    const pkgJson = path.join(modulesDir, pkgName, 'package.json');
    return JSON.parse(fs.readFileSync(pkgJson, 'utf8')).version;
  } catch {
    return null;
  }
}

if (!fs.existsSync(patchesDir)) process.exit(0);

let applied = 0;
let skipped = 0;

for (const entry of fs.readdirSync(patchesDir, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  // Имя папки: "<пакет>@<версия>". У scoped-пакетов в имени есть свой @,
  // поэтому режем по ПОСЛЕДНЕМУ.
  const at = entry.name.lastIndexOf('@');
  const pkgName = entry.name.slice(0, at);
  const wantVersion = entry.name.slice(at + 1);
  const have = installedVersion(pkgName);

  if (have === null) {
    console.warn(`[patches] ${pkgName} не установлен — патч пропущен`);
    skipped++;
    continue;
  }
  if (have !== wantVersion) {
    console.warn(
      `[patches] ВНИМАНИЕ: ${pkgName} установлен ${have}, а патч сделан для ${wantVersion}.\n` +
        `[patches] Патч НЕ применён. Проверьте, нужен ли он ещё, и обновите папку patches/.`,
    );
    skipped++;
    continue;
  }

  const srcRoot = path.join(patchesDir, entry.name);
  for (const src of walk(srcRoot)) {
    const rel = path.relative(srcRoot, src);
    const dst = path.join(modulesDir, pkgName, rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
    console.log(`[patches] ${pkgName}@${have}: ${rel.replace(/\\/g, '/')}`);
    applied++;
  }
}

console.log(`[patches] применено файлов: ${applied}, пропущено пакетов: ${skipped}`);
// Не роняем установку: если патч не встал, сборка всё равно упадёт, но уже
// с понятной причиной, а node_modules останется в целом состоянии.
