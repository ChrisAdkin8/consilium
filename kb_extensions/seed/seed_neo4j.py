"""
Seed Neo4j with a sample Terraform resource graph for local development.

Represents a simple AWS web-tier deployment:
  VPC → subnets → security group → EC2 instances → IAM instance profile → IAM role
  VPC → subnets → load balancer
  EC2 instances → S3 bucket (via IAM role)

Run:
  python -m kb_extensions.seed.seed_neo4j

Environment variables:
  NEO4J_URI   (default: bolt://127.0.0.1:7687)
  NEO4J_USER  (default: neo4j)
  NEO4J_PASS  (default: consilium-dev)
"""
import os
import sys

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASS", "consilium-dev")

RESOURCES = [
    {
        "id": "aws_vpc.main",
        "type": "aws_vpc",
        "provider": "aws",
        "public_access": False,
        "encrypted": None,
        "open_ports": None,
    },
    {
        "id": "aws_subnet.public_a",
        "type": "aws_subnet",
        "provider": "aws",
        "public_access": True,
        "encrypted": None,
        "open_ports": None,
    },
    {
        "id": "aws_subnet.private_a",
        "type": "aws_subnet",
        "provider": "aws",
        "public_access": False,
        "encrypted": None,
        "open_ports": None,
    },
    {
        "id": "aws_security_group.web",
        "type": "aws_security_group",
        "provider": "aws",
        "public_access": False,
        "encrypted": None,
        "open_ports": [80, 443],
    },
    {
        "id": "aws_iam_role.web_role",
        "type": "aws_iam_role",
        "provider": "aws",
        "public_access": False,
        "encrypted": None,
        "open_ports": None,
    },
    {
        "id": "aws_iam_instance_profile.web_profile",
        "type": "aws_iam_instance_profile",
        "provider": "aws",
        "public_access": False,
        "encrypted": None,
        "open_ports": None,
    },
    {
        "id": "aws_instance.web_1",
        "type": "aws_instance",
        "provider": "aws",
        "public_access": False,
        "encrypted": False,
        "open_ports": [80, 22],
    },
    {
        "id": "aws_instance.web_2",
        "type": "aws_instance",
        "provider": "aws",
        "public_access": False,
        "encrypted": False,
        "open_ports": [80],
    },
    {
        "id": "aws_s3_bucket.assets",
        "type": "aws_s3_bucket",
        "provider": "aws",
        "public_access": True,
        "encrypted": False,
        "open_ports": None,
    },
    {
        "id": "aws_lb.web_alb",
        "type": "aws_lb",
        "provider": "aws",
        "public_access": True,
        "encrypted": None,
        "open_ports": [80, 443],
    },
]

# (from_id, to_id) — from DEPENDS ON to
DEPENDS_ON_EDGES = [
    ("aws_subnet.public_a",            "aws_vpc.main"),
    ("aws_subnet.private_a",           "aws_vpc.main"),
    ("aws_security_group.web",         "aws_vpc.main"),
    ("aws_iam_instance_profile.web_profile", "aws_iam_role.web_role"),
    ("aws_instance.web_1",             "aws_subnet.private_a"),
    ("aws_instance.web_1",             "aws_security_group.web"),
    ("aws_instance.web_1",             "aws_iam_instance_profile.web_profile"),
    ("aws_instance.web_2",             "aws_subnet.private_a"),
    ("aws_instance.web_2",             "aws_security_group.web"),
    ("aws_instance.web_2",             "aws_iam_instance_profile.web_profile"),
    ("aws_lb.web_alb",                 "aws_subnet.public_a"),
    ("aws_lb.web_alb",                 "aws_security_group.web"),
]

IAM_PRINCIPALS = [
    {
        "arn": "arn:aws:iam::123456789012:role/web-role",
        "type": "Role",
    },
    {
        "arn": "arn:aws:iam::123456789012:user/admin",
        "type": "User",
    },
]

# (principal_arn, resource_id) — principal GRANTS access to resource
GRANTS_EDGES = [
    ("arn:aws:iam::123456789012:role/web-role",  "aws_instance.web_1"),
    ("arn:aws:iam::123456789012:role/web-role",  "aws_instance.web_2"),
    ("arn:aws:iam::123456789012:role/web-role",  "aws_s3_bucket.assets"),
    ("arn:aws:iam::123456789012:user/admin",     "aws_vpc.main"),
    ("arn:aws:iam::123456789012:user/admin",     "aws_s3_bucket.assets"),
    ("arn:aws:iam::123456789012:user/admin",     "aws_lb.web_alb"),
]


def _seed(tx) -> None:
    # Upsert Resource nodes
    for r in RESOURCES:
        tx.run(
            """
            MERGE (r:Resource {id: $id})
            SET r.type         = $type,
                r.provider     = $provider,
                r.public_access = $public_access,
                r.encrypted    = $encrypted,
                r.open_ports   = $open_ports
            """,
            **r,
        )

    # Upsert DEPENDS_ON edges
    for from_id, to_id in DEPENDS_ON_EDGES:
        tx.run(
            """
            MATCH (a:Resource {id: $from_id}), (b:Resource {id: $to_id})
            MERGE (a)-[:DEPENDS_ON]->(b)
            """,
            from_id=from_id,
            to_id=to_id,
        )

    # Upsert IamPrincipal nodes
    for p in IAM_PRINCIPALS:
        tx.run(
            """
            MERGE (p:IamPrincipal {arn: $arn})
            SET p.type = $type
            """,
            **p,
        )

    # Upsert GRANTS edges
    for principal_arn, resource_id in GRANTS_EDGES:
        tx.run(
            """
            MATCH (p:IamPrincipal {arn: $arn}), (r:Resource {id: $rid})
            MERGE (p)-[:GRANTS]->(r)
            """,
            arn=principal_arn,
            rid=resource_id,
        )


def main() -> None:
    print(f"[seed] connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    try:
        with driver.session() as session:
            session.execute_write(_seed)
        print(f"[seed] seeded {len(RESOURCES)} resources, {len(DEPENDS_ON_EDGES)} DEPENDS_ON edges,")
        print(f"[seed]        {len(IAM_PRINCIPALS)} IAM principals, {len(GRANTS_EDGES)} GRANTS edges.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
