# Working PoC for VULN-001: SQL injection
# Runtime: static
Payload: `?sort=name;DROP`
Attacker controls: sort query parameter across unauthenticated HTTP -> ORDER BY
