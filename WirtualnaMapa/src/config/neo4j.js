const neo4j = require('neo4j-driver');

// Sterownik powstaje przy pierwszym użyciu, więc aplikacja startuje także bez Neo4j (tryb plikowy).
let driver = null;

function getDriver() {
  if (!driver) {
    const { NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD } = process.env;
    driver = neo4j.driver(NEO4J_URI, neo4j.auth.basic(NEO4J_USER, NEO4J_PASSWORD));
  }
  return driver;
}

function getSession() {
  return getDriver().session({ database: process.env.NEO4J_DATABASE });
}

async function verifyNeo4j() {
  await getDriver().verifyConnectivity();
}

module.exports = { getDriver, getSession, verifyNeo4j };
