// by cause
MATCH (c:Cause {name:"Smoking"})-[:CAUSES]->(e:Effect)
OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(s:Source)
RETURN c.name AS cause, collect(distinct e.name) AS effects, collect(distinct s.title) AS sources;

// by effect
MATCH (e:Effect {name:"Lung cancer"})<-[:CAUSES]-(c:Cause)
OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(s:Source)
RETURN e.name AS effect, collect(distinct c.name) AS causes, collect(distinct s.title) AS sources;

// browse all (graph)
MATCH (c:Cause)-[r:CAUSES]->(e:Effect)
OPTIONAL MATCH (c)-[r2:EXTRACTED_FROM]->(s:Source)
RETURN c,r,e,r2,s
LIMIT 25;

// full-text search
CALL db.index.fulltext.queryNodes("cause_name_fts", "smok~")
YIELD node, score
RETURN node.name AS cause, score
ORDER BY score DESC
LIMIT 10;