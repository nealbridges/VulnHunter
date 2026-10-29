from flask import request


def ignored():
    return request.args.get("ghost")
