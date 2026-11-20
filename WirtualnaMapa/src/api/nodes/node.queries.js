module.exports = {
  getNodeWithConnections: `
    MATCH (n)
    WHERE id(n) = $id
    OPTIONAL MATCH (n)-[r]-(m)
    RETURN n, r, m
  `
};