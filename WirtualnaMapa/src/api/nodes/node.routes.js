const router = require('express').Router();
const controller = require('./node.controller');

router.get('/:id', controller.getNode);

module.exports = router;
