// --- 1) Unique constraints
CREATE CONSTRAINT cause_name_unique IF NOT EXISTS
FOR (c:Cause) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT effect_name_unique IF NOT EXISTS
FOR (e:Effect) REQUIRE e.name IS UNIQUE;

CREATE CONSTRAINT source_id_unique IF NOT EXISTS
FOR (s:Source) REQUIRE s.source_id IS UNIQUE;

// --- 2) Helpful indexes
CREATE INDEX source_title_idx IF NOT EXISTS
FOR (s:Source) ON (s.title);

// --- 3) Full-text indexes
CREATE FULLTEXT INDEX cause_name_fts IF NOT EXISTS
FOR (c:Cause) ON EACH [c.name];

CREATE FULLTEXT INDEX effect_name_fts IF NOT EXISTS
FOR (e:Effect) ON EACH [e.name];

// --- 4) Insert minimal MVP sample data
MERGE (c1:Cause  {name: "Smoking"})
MERGE (e1:Effect {name: "Lung cancer"})
MERGE (s1:Source {source_id: "paperA-2021", title: "Paper A (2021)"})
MERGE (c1)-[:CAUSES]->(e1)
MERGE (c1)-[:EXTRACTED_FROM]->(s1)
MERGE (e1)-[:EXTRACTED_FROM]->(s1);

MERGE (c2:Cause  {name: "Air pollution"})
MERGE (e2:Effect {name: "Asthma"})
MERGE (s2:Source {source_id: "paperB-2020", title: "Paper B (2020)"})
MERGE (c2)-[:CAUSES]->(e2)
MERGE (c2)-[:EXTRACTED_FROM]->(s2)
MERGE (e2)-[:EXTRACTED_FROM]->(s2);

// --- 5) Basic demo queries

// 5a) Given a cause, list effects and sources
MATCH (c:Cause {name:"Smoking"})-[:CAUSES]->(e:Effect)
OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(s:Source)
RETURN c.name AS cause, collect(distinct e.name) AS effects, collect(distinct s.title) AS sources;

// 5b) All cause->effect pairs (limit for visualization)
MATCH (c:Cause)-[:CAUSES]->(e:Effect)
RETURN c, e
LIMIT 25;

// 5c) For an effect, find possible causes + provenance
MATCH (e:Effect {name:"Lung cancer"})<-[:CAUSES]-(c:Cause)
OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(s:Source)
RETURN e.name AS effect, collect(distinct c.name) AS causes, collect(distinct s.title) AS sources;

// --- 6) Full-text search examples

// Search causes that look like "smok"
CALL db.index.fulltext.queryNodes("cause_name_fts", "smok~")
YIELD node, score
RETURN node.name AS cause, score
ORDER BY score DESC
LIMIT 10;

// Search effects that look like "cancer"
CALL db.index.fulltext.queryNodes("effect_name_fts", "cancer~")
YIELD node, score
RETURN node.name AS effect, score
ORDER BY score DESC
LIMIT 10;

// --- 7) Clean-up helper (optional, careful!)
/*
MATCH (n) DETACH DELETE n;
DROP CONSTRAINT cause_name_unique IF EXISTS;
DROP CONSTRAINT effect_name_unique IF EXISTS;
DROP CONSTRAINT source_id_unique IF EXISTS;
DROP INDEX source_title_idx IF EXISTS;
DROP INDEX cause_name_fts IF EXISTS;
DROP INDEX effect_name_fts IF EXISTS;
*/
