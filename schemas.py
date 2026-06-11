from pydantic import BaseModel, ConfigDict, Field


class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=50)


class PostCreate(PostBase):
    pass


class PostResponse(PostBase):
    # When configuring this model, Pydantic can read data from objects attributes,
    # not just dictionaries
    model_config = ConfigDict(from_attributes=True)

    id: int
    date_posted: str
