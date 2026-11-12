"""Demo source with sample jobs.

Used to test the matching and notification pipeline without any API key.
Replace/remove this once you have configured a real source.
"""
from __future__ import annotations

from datetime import date, timedelta

from models import Job
from sources.base import Source

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
LAST_WEEK = (date.today() - timedelta(days=6)).isoformat()

SAMPLE_JOBS = [
    Job(
        id="demo:sap-cds-amdp-developer-infosys",
        title="SAP CDS Views & AMDP Developer",
        company="Infosys Ltd.",
        location="Pune, India (Hybrid)",
        url="https://example.com/jobs/infosys-sap-cds-amdp",
        description=(
            "We are hiring an SAP CDS Views and AMDP specialist to design and "
            "optimize CDS Views and AMDP-based data models on SAP S/4HANA. "
            "Experience with SAP Datasphere, SAP Analytics Cloud, Fiori "
            "analytical apps and HANA Calculation Views is a plus."
        ),
        posted_at=TODAY,
        source="demo",
    ),
    Job(
        id="demo:sap-embedded-analytics-consultant-capgemini",
        title="SAP Embedded Analytics Consultant (CDS, AMDP, Datasphere)",
        company="Capgemini",
        location="Pune / Remote, India",
        url="https://example.com/jobs/capgemini-sap-embedded-analytics",
        description=(
            "Design SAP CDS Views, AMDP procedures and HANA Calculation Views "
            "for embedded analytics. Integrate with SAP Datasphere and SAP "
            "Analytics Cloud. Client-facing role for international engagements."
        ),
        posted_at=YESTERDAY,
        source="demo",
    ),
    Job(
        id="demo:sap-s4hana-abap-cds-developer-accenture",
        title="Senior SAP S/4HANA ABAP CDS Developer",
        company="Accenture",
        location="Remote, India",
        url="https://example.com/jobs/accenture-sap-abap-cds",
        description=(
            "ABAP CDS view development, AMDP stored procedures and RAP-based "
            "Fiori elements apps on SAP S/4HANA. SAP Datasphere exposure "
            "preferred."
        ),
        posted_at=TODAY,
        source="demo",
    ),
    Job(
        id="demo:sap-sac-datasphere-consultant-deloitte",
        title="SAP Analytics Cloud & Datasphere Consultant",
        company="Deloitte",
        location="Remote",
        url="https://example.com/jobs/deloitte-sac-datasphere",
        description=(
            "SAP Analytics Cloud stories, planning models and Datasphere "
            "spaces. CDS Views knowledge useful for data extraction from S/4HANA."
        ),
        posted_at=LAST_WEEK,
        source="demo",
    ),
    Job(
        id="demo:java-spring-boot-developer-tcs",
        title="Senior Java Spring Boot Developer",
        company="TCS",
        location="Bangalore, India",
        url="https://example.com/jobs/tcs-java-spring",
        description=(
            "Develop microservices with Java, Spring Boot and PostgreSQL. "
            "No SAP experience required."
        ),
        posted_at=TODAY,
        source="demo",
    ),
    Job(
        id="demo:marketing-executive",
        title="Marketing Executive",
        company="ABC Retail",
        location="Mumbai, India",
        url="https://example.com/jobs/marketing",
        description="Handle social media campaigns and content creation.",
        posted_at=TODAY,
        source="demo",
    ),
]


class DemoSource(Source):
    name = "demo"

    def fetch(self, queries):  # noqa: ARG002 - queries ignored for demo data
        return list(SAMPLE_JOBS)
