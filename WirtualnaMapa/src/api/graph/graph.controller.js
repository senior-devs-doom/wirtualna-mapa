const service = require('./graph.service');

async function getGraph(req, res, next) {
  try {
    res.json(await service.fetchGraph());
  } catch (e) {
    next(e);
  }
}

module.exports = { getGraph };