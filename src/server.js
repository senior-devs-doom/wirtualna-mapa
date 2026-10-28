require('dotenv').config();
const path = require('path');
const express = require('express');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

// static frontend - no-store while this is under active development: a
// browser silently serving a stale cached index.html/JS after an edit reads
// as a phantom bug (a fix that "isn't working"), the same class of problem
// the /photos no-store below already exists to prevent
app.use(express.static(path.join(__dirname, '../public'), {
  setHeaders: res => res.setHeader('Cache-Control', 'no-store'),
}));

// fuzzy-search library served from node_modules (no CDN dependency at runtime)
app.use('/vendor/fuse', express.static(path.join(__dirname, '../node_modules/fuse.js/dist'), {
  setHeaders: res => res.setHeader('Cache-Control', 'no-store'),
}));

// real 360 photos, named by Location.name - served straight from tools/,
// not duplicated into public/img. no-store: these get overwritten in place
// by the calibration tool, and a browser silently serving a stale cached
// copy after that (rather than a normal 304 revalidation) is exactly what
// caused "I corrected it, navigated away, came back, angle's wrong again"
app.use('/photos', express.static(path.join(__dirname, '../photos_360'), {
  setHeaders: res => res.setHeader('Cache-Control', 'no-store'),
}));

// bramy IPFS, z których przeglądarka pobiera zdjęcia (po kolei, pierwsza działająca);
// nadpisywane zmienną IPFS_GATEWAYS (lista po przecinku, każda kończy się "/ipfs/"),
// np. dedykowana brama z konta Pinata
// 1. dedykowana brama konta Pinata (zmierzone: pierwszy bajt ~0,8 s, bez limitu żądań),
// 2. publiczna brama Pinata (~5 s do pierwszego bajtu, limit ok. 40 żądań, potem 429),
// 3. publiczne bramy ogólne (zawodne pod obciążeniem, tylko ostatnia deska ratunku)
const DEFAULT_IPFS_GATEWAYS = [
  'https://plum-active-cardinal-914.mypinata.cloud/ipfs/',
  'https://gateway.pinata.cloud/ipfs/',
  'https://ipfs.io/ipfs/',
];
app.get('/api/config', (req, res) => {
  const fromEnv = (process.env.IPFS_GATEWAYS || '').split(',').map(g => g.trim()).filter(Boolean);
  res.json({ ipfsGateways: fromEnv.length ? fromEnv : DEFAULT_IPFS_GATEWAYS });
});

// API
const graphRoutes = require('./api/graph/graph.routes');
const nodeRoutes = require('./api/nodes/node.routes');
const pathRoutes = require('./api/path/path.routes');

app.use('/api/graph', graphRoutes);
app.use('/api/nodes', nodeRoutes);
app.use('/api/path', pathRoutes);

// root -> index.html
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../public/index.html'));
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
