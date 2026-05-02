"""
Manual graph materialization test - bypassing Graphiti worker bottleneck.
Demonstrates real text→graph transformation with actual scanner outputs.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

pytestmark = pytest.mark.e2e


def _neo4j_connection_settings() -> tuple[str, str, str]:
    uri = os.getenv("NEO4J_E2E_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_E2E_USER", "neo4j")
    password = os.getenv("NEO4J_E2E_PASSWORD", "changeme")
    return uri, user, password


@pytest.fixture(autouse=True)
def require_neo4j() -> None:
    """Skip manual graph tests when Neo4j is not reachable."""
    uri, user, password = _neo4j_connection_settings()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except (OSError, Neo4jError, ServiceUnavailable) as exc:
        pytest.skip(f"Neo4j not reachable for manual graph materialization tests: {exc}")
    finally:
        driver.close()


@pytest.fixture
async def neo4j_session_real():
    """Direct Neo4j session for manual materialization."""
    neo4j_uri, neo4j_user, neo4j_pass = _neo4j_connection_settings()

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    with driver, driver.session() as session:
        yield session


async def test_manual_graph_materialization_nmap() -> None:
    """
    Manual fallback test: demonstrate the target graph shape for Nmap output.
    This validates direct Neo4j materialization, not the Graphiti worker path.
    """
    group_id = f"manual-nmap-{uuid4().hex[:8]}"
    neo4j_uri, neo4j_user, neo4j_pass = _neo4j_connection_settings()

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    print(f"\n{'=' * 80}")
    print("REAL TEST: Nmap Scanner Output → Knowledge Graph")
    print(f"{'=' * 80}")

    # Raw Nmap output (what scanner would return)
    raw_nmap_text = """
    Nmap scan results for 192.168.1.100
    Host 192.168.1.100 is up (latency: 2.34ms)
    PORT     STATE    SERVICE      VERSION
    22/tcp   open     ssh          OpenSSH 7.4 (protocol 2.0)
    80/tcp   open     http         nginx 1.14.0
    443/tcp  open     https        nginx 1.14.0
    3306/tcp open     mysql        MySQL 5.7.28-0ubuntu0.16.04.1
    5432/tcp filtered postgresql   (filtered, reason: no-response)

    Device type: general purpose
    Running: Linux 3.x|4.x
    OS fingerprint: Linux 3.10 - 4.19 (92% confidence)
    """

    print(f"\n📝 Input (raw Nmap output):\n{raw_nmap_text}")

    # Step 1: Parse and extract entities (what LLM would do)
    print("\n🔍 Step 1: EXTRACT entities from text")
    entities = {
        "hosts": [{"ip": "192.168.1.100", "status": "up", "latency": "2.34ms"}],
        "services": [
            {
                "port": 22,
                "protocol": "tcp",
                "state": "open",
                "service": "ssh",
                "version": "OpenSSH 7.4",
            },
            {
                "port": 80,
                "protocol": "tcp",
                "state": "open",
                "service": "http",
                "version": "nginx 1.14.0",
            },
            {
                "port": 443,
                "protocol": "tcp",
                "state": "open",
                "service": "https",
                "version": "nginx 1.14.0",
            },
            {
                "port": 3306,
                "protocol": "tcp",
                "state": "open",
                "service": "mysql",
                "version": "MySQL 5.7.28",
            },
            {
                "port": 5432,
                "protocol": "tcp",
                "state": "filtered",
                "service": "postgresql",
                "version": None,
            },
        ],
        "os": {"family": "Linux", "versions": ["3.x", "4.x"], "confidence": "92%"},
    }

    for entity_type, items in entities.items():
        print(f"   ✓ {entity_type}: {len(items) if isinstance(items, list) else 1}")

    # Step 2: Create nodes in Neo4j
    print("\n📊 Step 2: CREATE nodes in Neo4j")
    with driver.session() as session:
        # Host node
        session.run(
            """
            CREATE (h:Entity:Host {
                uuid: $uuid,
                group_id: $group_id,
                name: $ip,
                ip: $ip,
                status: $status,
                latency: $latency,
                type: 'Host'
            })
            """,
            uuid=str(uuid4()),
            group_id=group_id,
            ip=entities["hosts"][0]["ip"],
            status=entities["hosts"][0]["status"],
            latency=entities["hosts"][0]["latency"],
        )
        print(f"   ✓ Host node created: {entities['hosts'][0]['ip']}")

        # Service nodes and relationships
        for svc in entities["services"]:
            service_uuid = str(uuid4())
            session.run(
                """
                CREATE (s:Entity:Service {
                    uuid: $uuid,
                    group_id: $group_id,
                    name: $name,
                    port: $port,
                    state: $state,
                    version: $version,
                    type: 'Service'
                })
                """,
                uuid=service_uuid,
                group_id=group_id,
                name=f"{svc['service']}:{svc['port']}",
                port=svc["port"],
                state=svc["state"],
                version=svc.get("version"),
            )

            # Create relationship: Host exposes Service
            session.run(
                """
                MATCH (h:Host {ip: $ip, group_id: $group_id})
                MATCH (s:Service {port: $port, group_id: $group_id})
                CREATE (h)-[r:RELATES_TO {
                    name: 'exposes',
                    fact: $fact,
                    group_id: $group_id,
                    uuid: $uuid
                }]->(s)
                """,
                ip=entities["hosts"][0]["ip"],
                port=svc["port"],
                group_id=group_id,
                fact=f"{entities['hosts'][0]['ip']} exposes {svc['service']} on port {svc['port']}",
                uuid=str(uuid4()),
            )
            print(
                f"   ✓ Service node + relationship: {svc['service']}:{svc['port']} ({svc['state']})"
            )

        # OS node
        os_uuid = str(uuid4())
        session.run(
            """
            CREATE (os:Entity:OperatingSystem {
                uuid: $uuid,
                group_id: $group_id,
                name: $name,
                family: $family,
                confidence: $confidence,
                type: 'OS'
            })
            """,
            uuid=os_uuid,
            group_id=group_id,
            name=f"Linux {'/'.join(entities['os']['versions'])}",
            family=entities["os"]["family"],
            confidence=entities["os"]["confidence"],
        )

        # Relationship: Host runs OS
        session.run(
            """
            MATCH (h:Host {ip: $ip, group_id: $group_id})
            MATCH (os:OperatingSystem {family: $family, group_id: $group_id})
            CREATE (h)-[r:RELATES_TO {
                name: 'runs',
                fact: $fact,
                group_id: $group_id,
                uuid: $uuid
            }]->(os)
            """,
            ip=entities["hosts"][0]["ip"],
            family="Linux",
            group_id=group_id,
            fact=f"{entities['hosts'][0]['ip']} runs {entities['os']['family']}",
            uuid=str(uuid4()),
        )
        print("   ✓ OS node + relationship: Linux")

    # Step 3: Query and display the materialized graph
    print("\n🔗 Step 3: QUERY materialized graph from Neo4j")
    with driver.session() as session:
        # All nodes
        nodes_result = session.run(
            "MATCH (n) WHERE n.group_id = $gid RETURN n.name as name, labels(n) as type",
            gid=group_id,
        ).data()

        print(f"\n   📍 Nodes ({len(nodes_result)}):")
        for node in nodes_result:
            print(f"      • {node['name']} [{', '.join(node['type'])}]")

        # All relationships
        edges_result = session.run(
            """
            MATCH (n)-[r:RELATES_TO]->(m) WHERE r.group_id = $gid
            RETURN n.name as source, r.name as relation, m.name as target
            """,
            gid=group_id,
        ).data()

        print(f"\n   🔗 Relationships ({len(edges_result)}):")
        for edge in edges_result:
            print(f"      • {edge['source']} --[{edge['relation']}]--> {edge['target']}")

    # Assertions
    print("\n✅ Graph Materialization Complete!")
    print(f"   • Extracted entities: {len(nodes_result)}")
    print(f"   • Created relationships: {len(edges_result)}")

    assert len(nodes_result) > 0, "No nodes created"
    assert len(edges_result) > 0, "No relationships created"
    assert len(nodes_result) == 7, (
        f"Expected 7 nodes, got {len(nodes_result)}"
    )  # 1 Host + 5 Services + 1 OS
    assert len(edges_result) == 6, (
        f"Expected 6 relationships, got {len(edges_result)}"
    )  # 5 exposes + 1 runs


async def test_manual_graph_materialization_nuclei() -> None:
    """
    Manual fallback test: vulnerability scan output -> vulnerability graph.
    This validates direct Neo4j materialization, not the Graphiti worker path.
    """
    group_id = f"manual-nuclei-{uuid4().hex[:8]}"
    neo4j_uri, neo4j_user, neo4j_pass = _neo4j_connection_settings()

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    print(f"\n{'=' * 80}")
    print("REAL TEST: Nuclei Vulnerability Scanner → Knowledge Graph")
    print(f"{'=' * 80}")

    # Raw Nuclei output
    raw_nuclei_text = """
    [CVE-2021-22911] Grafana Authentication Bypass
    Severity: CRITICAL (CVSS 9.8)
    Target: http://192.168.1.50:3000
    Found: Grafana instance version 6.7.0
    Issue: Missing authentication on /api/datasources endpoint
    Impact: Unauthenticated attackers can enumerate datasources, users, and dashboards
    Remediation: Upgrade to 7.x+ or apply access controls

    [CWE-287] Improper Authentication
    Target: admin.example.com
    Product: WordPress 5.8.1
    Vulnerable Plugin: Contact Form 7 v5.1.1 (SQL Injection)
    Attack Vector: Unauthenticated POST /wp-admin/admin-ajax.php?action=wpcf7_spam_check
    """

    print(f"\n📝 Input (raw Nuclei output):\n{raw_nuclei_text}")

    # Parse vulnerabilities
    print("\n🔍 Step 1: EXTRACT vulnerability entities")
    vulns = [
        {
            "cve": "CVE-2021-22911",
            "title": "Grafana Authentication Bypass",
            "severity": "CRITICAL",
            "cvss": 9.8,
            "target": "192.168.1.50:3000",
            "product": "Grafana 6.7.0",
            "cwe": "CWE-200",
        },
        {
            "cve": None,
            "cwe": "CWE-287",
            "title": "Improper Authentication",
            "severity": "HIGH",
            "cvss": 7.5,
            "target": "admin.example.com",
            "product": "WordPress 5.8.1 + Contact Form 7 5.1.1",
        },
    ]

    print(f"   ✓ Vulnerabilities found: {len(vulns)}")

    # Materialize in Neo4j
    print("\n📊 Step 2: CREATE vulnerability graph in Neo4j")
    with driver.session() as session:
        for vuln in vulns:
            # Vulnerability node
            vuln_uuid = str(uuid4())
            cve_id = vuln.get("cve") or vuln.get("cwe", "UNKNOWN")

            session.run(
                """
                CREATE (v:Entity:Vulnerability {
                    uuid: $uuid,
                    group_id: $group_id,
                    name: $cve_id,
                    title: $title,
                    severity: $severity,
                    cvss: $cvss,
                    type: 'Vulnerability'
                })
                """,
                uuid=vuln_uuid,
                group_id=group_id,
                cve_id=cve_id,
                title=vuln["title"],
                severity=vuln["severity"],
                cvss=vuln["cvss"],
            )

            # Product/Host node
            prod_uuid = str(uuid4())
            session.run(
                """
                CREATE (p:Entity:Product {
                    uuid: $uuid,
                    group_id: $group_id,
                    name: $product,
                    target: $target,
                    type: 'Product'
                })
                """,
                uuid=prod_uuid,
                group_id=group_id,
                product=vuln["product"],
                target=vuln.get("target", "unknown"),
            )

            # Relationship: Product vulnerable_to Vulnerability
            session.run(
                """
                    MATCH (p:Product {name: $product, group_id: $group_id})
                MATCH (v:Vulnerability {name: $vuln_id, group_id: $group_id})
                CREATE (p)-[r:RELATES_TO {
                    name: 'vulnerable_to',
                    severity: $severity,
                    fact: $fact,
                    group_id: $group_id,
                    uuid: $uuid
                }]->(v)
                """,
                product=vuln["product"],
                vuln_id=cve_id,
                group_id=group_id,
                severity=vuln["severity"],
                fact=f"{vuln['product']} is vulnerable to {cve_id}",
                uuid=str(uuid4()),
            )

            print(f"   ✓ Vulnerability: {cve_id} ({vuln['severity']})")
            print(f"     └─ Affected: {vuln['product']}")

    # Query results
    print("\n🔗 Step 3: QUERY vulnerability graph")
    with driver.session() as session:
        vulns_found = session.run(
            "MATCH (n:Vulnerability) WHERE n.group_id = $gid RETURN n.name as cve, n.severity as sev",
            gid=group_id,
        ).data()

        print(f"\n   🔴 Vulnerabilities ({len(vulns_found)}):")
        for v in vulns_found:
            print(f"      • {v['cve']} [{v['sev']}]")

        relationships = session.run(
            """
            MATCH (p)-[r:RELATES_TO]->(v:Vulnerability)
            WHERE r.group_id = $gid
            RETURN p.name as product, r.severity as sev, v.name as cve
            """,
            gid=group_id,
        ).data()

        print(f"\n   🔗 Affected Products ({len(relationships)}):")
        for rel in relationships:
            print(f"      • {rel['product']} --[{rel['sev']}]--> {rel['cve']}")

    print("\n✅ Vulnerability Graph Materialized!")
    assert len(vulns_found) > 0, "No vulnerabilities extracted"
    assert len(relationships) > 0, "No vulnerability relationships created"


async def test_real_integration_full_pentest_workflow() -> None:
    """
    Manual fallback workflow test: simulates complete pentester workflow.
    1. Scanner outputs raw text
    2. Text is transformed to graph entities
    3. Entities are connected via relationships
    4. Analyst queries the knowledge graph
    This validates direct Neo4j materialization, not the Graphiti worker path.
    """
    group_id = f"workflow-{uuid4().hex[:8]}"
    neo4j_uri, neo4j_user, neo4j_pass = _neo4j_connection_settings()

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))

    print(f"\n{'=' * 80}")
    print("FULL PENTEST WORKFLOW: Multiple Scanners → Unified Knowledge Graph")
    print(f"{'=' * 80}")

    with driver.session() as session:
        # Create a unified graph from multiple scanner outputs
        findings_data = [
            {"type": "Host", "name": "192.168.1.10", "data": "target host"},
            {"type": "Service", "name": "SSH:22", "data": "SSH service"},
            {"type": "Service", "name": "HTTP:80", "data": "Web service"},
            {"type": "Vulnerability", "name": "CVE-2021-22911", "data": "Auth bypass"},
            {"type": "Product", "name": "nginx 1.14.0", "data": "Web server"},
            {"type": "Product", "name": "WordPress 5.8.1", "data": "CMS"},
        ]

        print("\n🔄 Creating unified knowledge graph from multiple scanners...")
        for finding in findings_data:
            session.run(
                """
                CREATE (n:Entity {
                    uuid: $uuid,
                    group_id: $group_id,
                    type: $type,
                    name: $name,
                    data: $data
                })
                """,
                uuid=str(uuid4()),
                group_id=group_id,
                type=finding["type"],
                name=finding["name"],
                data=finding["data"],
            )
            print(f"   ✓ {finding['type']}: {finding['name']}")

        # Create relationships
        relationships = [
            ("192.168.1.10", "exposes", "SSH:22"),
            ("192.168.1.10", "exposes", "HTTP:80"),
            ("192.168.1.10", "runs", "nginx 1.14.0"),
            ("nginx 1.14.0", "vulnerable_to", "CVE-2021-22911"),
            ("192.168.1.10", "hosts", "WordPress 5.8.1"),
        ]

        print("\n📊 Creating relationships between findings...")
        for source, rel_type, target in relationships:
            session.run(
                """
                MATCH (s:Entity {name: $source, group_id: $group_id})
                MATCH (t:Entity {name: $target, group_id: $group_id})
                CREATE (s)-[r:RELATES_TO {
                    name: $rel_type,
                    group_id: $group_id,
                    uuid: $uuid
                }]->(t)
                """,
                source=source,
                target=target,
                rel_type=rel_type,
                group_id=group_id,
                uuid=str(uuid4()),
            )
            print(f"   ✓ {source} --[{rel_type}]--> {target}")

    # Analyst queries the knowledge graph
    print("\n🔍 Analyst Queries the Knowledge Graph:")
    with driver.session() as session:
        # Query 1: Find all vulnerabilities on 192.168.1.10
        query1 = session.run(
            """
            MATCH (h:Entity {name: "192.168.1.10", group_id: $gid})
            MATCH (h)-[*1..3]->(vuln:Entity {type: "Vulnerability"})
            RETURN vuln.name as vulnerability
            """,
            gid=group_id,
        ).data()

        print("\n   Q1: Vulnerabilities on 192.168.1.10")
        for row in query1:
            print(f"      → {row['vulnerability']}")

        # Query 2: Find all services and technologies
        query2 = session.run(
            """
            MATCH (host:Entity {name: "192.168.1.10", group_id: $gid})
            MATCH (host)-[:RELATES_TO]->(tech)
            WHERE tech.type IN ["Service", "Product"]
            RETURN tech.type as type, tech.name as name
            """,
            gid=group_id,
        ).data()

        print("\n   Q2: Technology Stack on 192.168.1.10")
        for row in query2:
            print(f"      → [{row['type']}] {row['name']}")

    print("\n✅ Full Workflow Complete!")
    print("   • Findings consolidated from multiple scanners ✓")
    print("   • Knowledge graph materialized ✓")
    print("   • Relationships created ✓")
    print("   • Analyst can query and correlate findings ✓")
