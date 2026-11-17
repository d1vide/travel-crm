from pydantic import BaseModel, ConfigDict


class Dto(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, hide_input_in_errors=True)
