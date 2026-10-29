import argparse
import os

from flask import Flask, request

app = Flask(__name__)
parser = argparse.ArgumentParser()


@app.route("/users/<int:user_id>")
def view(user_id: str) -> str:
    name = request.args.get("name", "")
    tag = request.args["tag"]
    q = request.query_params.get("q")
    old = request.GET.get("old")
    old2 = request.GET["old2"]
    form = request.form.get("form")
    form2 = request.form["form2"]
    post = request.POST.get("post")
    post2 = request.POST["post2"]
    auth = request.headers.get("Authorization")
    auth2 = request.headers["X-Key"]
    meta = request.META.get("HTTP_X_FORWARDED_FOR")
    cookie = request.cookies.get("session")
    cookie2 = request.COOKIES.get("theme")
    body = request.get_json()["email"]
    body2 = request.get_json().get("phone")
    body3 = request.json["role"]
    body4 = request.json.get("scope")
    body5 = request.data["raw"]
    home = os.environ.get("HOME", "")
    key = os.environ.get("API_KEY") or ""
    token = os.getenv("TOKEN") or ""
    parser.add_argument("--verbose")
    parser.add_argument("positional")
    return " ".join(
        [
            user_id,
            name,
            tag,
            q,
            old,
            old2,
            form,
            form2,
            post,
            post2,
            auth,
            auth2,
            meta,
            cookie,
            cookie2,
            body,
            body2,
            body3,
            body4,
            body5,
            home,
            key,
            token,
        ]
    )
