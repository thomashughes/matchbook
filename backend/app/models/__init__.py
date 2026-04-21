# Re-export every ORM model here so Alembic's autogenerate sees them all
# with a single `from app.models import *` in alembic/env.py.
from app.models.base import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.profile import Profile, ProfileAnswer  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.job_score import JobScore  # noqa: F401
from app.models.cover_letter import CoverLetter  # noqa: F401
from app.models.job_ai_output import JobAIOutput  # noqa: F401
from app.models.interview import InterviewEvent  # noqa: F401
from app.models.company_research import CompanyResearchCache  # noqa: F401
from app.models.usage_counter import UsageCounter  # noqa: F401
from app.models.cv_version import CvVersion  # noqa: F401
