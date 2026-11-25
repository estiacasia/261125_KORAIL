import math

from flask import Blueprint, abort, render_template, request

from ..catalog import catalog_rev
from ..extensions import db
from ..models import History
from .api import get_catalog, history_dict, history_query, settings_dict

bp = Blueprint("pages", __name__)


@bp.get("/")
def generator():
    return render_template("generator.html", boot={"rev": catalog_rev(), "settings": settings_dict()})


@bp.get("/history")
def history():
    q = history_query(request.args)
    per = 20
    page = max(request.args.get("page", 1, type=int), 1)
    total = q.count()
    items = [history_dict(h) for h in q.offset((page - 1) * per).limit(per).all()]
    cat = get_catalog()
    sits = [(m, code, cat[m]["sits"][code]["name"]) for m in ("email", "notice") for code in cat[m]["order"]]
    return render_template("history.html", items=items, total=total, page=page, pages=max(1, math.ceil(total / per)),
                           args=request.args, sits=sits)


@bp.get("/history/<int:hid>")
def history_detail(hid):
    h = db.session.get(History, hid)
    if not h:
        abort(404)
    return render_template("history_detail.html", h=history_dict(h, full=True))


@bp.get("/contacts")
def contacts():
    return render_template("contacts.html")


@bp.get("/catalog")
def catalog_admin():
    return render_template("catalog_admin.html")


@bp.get("/settings")
def settings():
    return render_template("settings.html", s=settings_dict())
