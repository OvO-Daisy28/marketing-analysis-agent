from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Dimension = Literal["month", "traffic_type", "visitor_type", "region", "weekend"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(Strict):
    month: list[
        Literal["Jan", "Feb", "Mar", "Apr", "May", "June", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    ] = Field(default_factory=list, max_length=12)
    traffic_type: list[int] = Field(default_factory=list, max_length=20)
    visitor_type: list[Literal["New_Visitor", "Returning_Visitor", "Other"]] = Field(
        default_factory=list, max_length=3
    )
    region: list[int] = Field(default_factory=list, max_length=9)
    weekend: list[bool] = Field(default_factory=list, max_length=2)


class Query(Strict):
    group_by: list[Dimension] = Field(default_factory=list, max_length=2)
    filters: Filters = Field(default_factory=Filters)

    @model_validator(mode="after")
    def unique_dimensions(self):
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("group_by cannot repeat a dimension")
        return self


class ReportSpec(Strict):
    title: str = Field(min_length=1, max_length=120)
    intro_html: str = Field(default="<p>营销数据分析报告</p>", max_length=4000)
    chart: Literal["bar", "line", "table"] = "bar"
    metric: Literal["sessions", "purchases", "conversion_rate"] = "conversion_rate"
    claim_ids: list[str] = Field(default_factory=list, max_length=20)


class NewGoal(Strict):
    objective: str = Field(min_length=3, max_length=3000)
    mode: Literal["report", "research"] = "report"
    criteria: list[str] = Field(default_factory=list, max_length=8)
    request_key: str = Field(min_length=8, max_length=100)


class ContinueRun(Strict):
    instruction: str = Field(min_length=1, max_length=3000)
    request_key: str = Field(min_length=8, max_length=100)


class Revision(Strict):
    base_version_id: str | None = None
    spec: ReportSpec
    query: Query | None = None
    request_key: str = Field(min_length=8, max_length=100)


class Credentials(Strict):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=10, max_length=128)
