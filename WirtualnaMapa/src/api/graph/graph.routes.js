const router = require('express').Router();
const controller = require('./graph.controller');

router.get('/', controller.getGraph);

module.exports = router;