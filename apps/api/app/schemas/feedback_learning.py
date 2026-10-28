from pydantic import BaseModel, ConfigDict


class FeedbackLearningRefresh(BaseModel):
    """Only refresh current owned sources; callers cannot inject evidence."""
    model_config = ConfigDict(extra="forbid")
