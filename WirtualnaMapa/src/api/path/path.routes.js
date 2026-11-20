const express = require('express');
const router = express.Router();
const controller = require('./path.controller');

router.post('/', controller.postPath);

module.exports = router;
