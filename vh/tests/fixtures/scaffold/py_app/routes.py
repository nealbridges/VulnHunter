import click
from django.urls import path, re_path
from fastapi import APIRouter, Cookie, Form, Header, Path, Query
from flask import request
from models import LoginBody, Payload


class Session:
    pass


class User:
    pass


router = APIRouter()


class UnknownBody:
    """Not a model: the pack reports this annotation unresolved."""


def view():
    return request


@router.get("/items/{item_id}")
async def item(item_id: str):
    return item_id


@click.command()
@click.option("--flag")
def cli(flag: str):
    return flag


urlpatterns = [
    path("users/<int:pk>/", view),
    re_path(r"^tags/(?P<slug>[\w-]+)/$", view),
]


@router.post("/login")
async def login(body: LoginBody, missing: UnknownBody):
    return body, missing


@router.post("/optional")
def optional(body: LoginBody | None, other: Payload | None = None):
    return body, other


def helper(db: Session, user: User):
    return db, user


@router.put("/payload")
def put(
    payload: Payload,
    q: str = Query(...),
    x: str = Path(...),
    h: str = Header(...),
    c: str = Cookie(...),
    f: str = Form(...),
):
    return payload, q, x, h, c, f
