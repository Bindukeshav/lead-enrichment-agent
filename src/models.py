"""Structured output schemas for the lead enrichment agent."""
from typing import Optional
from pydantic import BaseModel, Field


class TeamMember(BaseModel):
    name: str = Field(description="Full name of the leadership/team member")
    role: Optional[str] = Field(default=None, description="Job title or role")
    linkedin_url: Optional[str] = Field(
        default=None, description="LinkedIn profile URL, if discoverable"
    )


class LeadEnrichmentResult(BaseModel):
    domain: str = Field(description="The company domain that was scraped")
    company_overview: str = Field(
        description="A concise 2-sentence summary of what the company does"
    )
    target_audience: str = Field(
        description="Who the product/service is built for (their ICP)"
    )
    contact_points: list[str] = Field(
        default_factory=list,
        description="Generic/public emails found on the site (contact@, sales@, etc.)",
    )
    key_team_members: list[TeamMember] = Field(
        default_factory=list,
        description="Leadership/team members with role and LinkedIn URL if found",
    )
    data_confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Estimated confidence/completeness of the extracted data",
    )


class ScrapeError(BaseModel):
    """Used when a domain fails so the pipeline can record it without crashing."""

    domain: str
    error: str
    stage: str  # e.g. "fetch", "extract"
