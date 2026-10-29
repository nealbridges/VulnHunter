from flask import request


def mixed_py():
    return request.args.get("q")
