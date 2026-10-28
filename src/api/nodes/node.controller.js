const service = require('./node.service');

async function getNode(req, res, next) {
  try {
    const node = await service.fetchNode(Number(req.params.id));
    if (!node) return res.status(404).json({ error: 'Not found' });
    res.json(node);
  } catch (e) {
    next(e);
  }
}

module.exports = { getNode };
