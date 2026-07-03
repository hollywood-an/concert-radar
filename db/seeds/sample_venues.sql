-- Seed: 5 sample venues in Columbus, OH. Coordinates are approximate (sample data).
INSERT INTO venues (name, location, address, city, state, country, capacity)
SELECT v.name, v.location, v.address, 'Columbus', 'OH', 'US', v.capacity
FROM (
    VALUES
        ('Newport Music Hall',
         ST_SetSRID(ST_MakePoint(-83.00830, 39.99790), 4326)::geography,
         '{"street": "1722 N High St", "zip": "43201"}'::jsonb, 1700),
        ('Ace of Cups',
         ST_SetSRID(ST_MakePoint(-83.01260, 40.01460), 4326)::geography,
         '{"street": "2619 N High St", "zip": "43202"}'::jsonb, 350),
        ('The Basement',
         ST_SetSRID(ST_MakePoint(-83.01170, 39.96890), 4326)::geography,
         '{"street": "391 Neil Ave", "zip": "43215"}'::jsonb, 300),
        ('KEMBA Live!',
         ST_SetSRID(ST_MakePoint(-83.01180, 39.96960), 4326)::geography,
         '{"street": "405 Neil Ave", "zip": "43215"}'::jsonb, 5200),
        ('Nationwide Arena',
         ST_SetSRID(ST_MakePoint(-83.00600, 39.96950), 4326)::geography,
         '{"street": "200 W Nationwide Blvd", "zip": "43215"}'::jsonb, 20000)
) AS v(name, location, address, capacity)
WHERE NOT EXISTS (SELECT 1 FROM venues existing WHERE existing.name = v.name);
