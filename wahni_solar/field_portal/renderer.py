"""Serve the Wahni Field service worker at /field/sw.js.

A worker controls only URLs under its own path, so it cannot be served from
/assets/... and still control /field/. The /field/<path> route rule would
otherwise answer this URL with the SPA HTML.
"""

import os

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

WORKER_PATH = "/field/sw.js"


def worker_file():
    return os.path.join(frappe.get_app_path("wahni_solar"), "public", "field", "sw.js")


class FieldWorkerRenderer(BaseRenderer):
    def can_render(self):
        request = getattr(frappe.local, "request", None)
        return bool(request and request.path == WORKER_PATH)

    def render(self):
        path = worker_file()
        if not os.path.exists(path):
            return Response("Not Found", status=404, mimetype="text/plain")
        with open(path, "rb") as worker:
            body = worker.read()
        response = Response(body, status=200, mimetype="application/javascript")
        response.headers["Service-Worker-Allowed"] = "/field/"
        # Browsers must always revalidate the worker so updates are noticed.
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
