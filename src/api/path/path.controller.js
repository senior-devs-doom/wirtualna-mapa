const service = require('./path.service');

async function postPath(req, res, next) {
  try {
    const { from, to, flags } = req.body || {};
    const toValid = typeof to === 'string' ||
      (Array.isArray(to) && to.length > 0 && to.every(t => typeof t === 'string'));
    if (!from || !toValid) {
      return res.status(400).json({ error: 'from and to (name or non-empty array of names) are required' });
    }
    const result = await service.findPath(from, to, flags || {});
    if (!result) return res.status(404).json({ error: 'No path found' });
    res.json(result);
  } catch (e) {
    if (e.message.startsWith('Unknown')) {
      return res.status(404).json({ error: e.message });
    }
    next(e);
  }
}

module.exports = { postPath };
