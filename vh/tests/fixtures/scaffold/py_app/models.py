from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class LoginBody:
    username: str
    email: str


class Payload(BaseModel):
    role: str
    scope: str
