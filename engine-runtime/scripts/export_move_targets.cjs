#!/usr/bin/env node
/**
 * Export move id -> Showdown target from Dex.forFormat(battle_format).
 * Usage: node export_move_targets.cjs <pokemon-showdown-root> <battle_format>
 * Writes JSON to stdout.
 */
const fs = require('fs');
const path = require('path');

const showdownRoot = process.argv[2];
const battleFormat = process.argv[3];
if (!showdownRoot || !battleFormat) {
  process.stderr.write(
    'usage: node export_move_targets.cjs <pokemon-showdown-root> <battle_format>\n',
  );
  process.exit(1);
}

function loadDex() {
  const dexPath = path.join(showdownRoot, 'dist', 'sim', 'dex.js');
  if (!fs.existsSync(dexPath)) {
    throw new Error(
      `SHOWDOWN_DEX_NOT_BUILT: missing ${dexPath} (run node build in pokemon-showdown)`,
    );
  }
  // eslint-disable-next-line import/no-dynamic-require, global-require
  return require(dexPath).Dex;
}

try {
  const Dex = loadDex();
  const dex = Dex.forFormat(battleFormat);
  const moves = {};
  for (const id of Object.keys(dex.data.Moves)) {
    const move = dex.data.Moves[id];
    if (!move || !move.target) {
      continue;
    }
    moves[id] = { name: move.name, target: move.target };
  }
  const fingerprint = `${battleFormat}:${Object.keys(moves).length}`;
  process.stdout.write(
    JSON.stringify({
      battleFormat,
      fingerprint,
      source: 'showdown-dex',
      moves,
    }),
  );
} catch (err) {
  process.stderr.write(String(err.message || err));
  process.exit(2);
}
