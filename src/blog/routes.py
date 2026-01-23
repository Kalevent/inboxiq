from flask import render_template, url_for, abort

from src.blog import bp
from .services import load_blog_post, load_blog_posts


@bp.route("/", methods=["GET"])
def blog_index():
  posts = load_blog_posts()
  return render_template("blog.html", posts=posts)


@bp.route("/<slug>", methods=["GET"])
def blog_post(slug):
  post = load_blog_post(slug)
  if not post:
    return abort(404)
  canonical = post.get("canonical_url")
  if canonical and not canonical.startswith("http"):
    canonical_url = url_for("blog.blog_post", slug=slug, _external=True)
  else:
    canonical_url = canonical or url_for("blog.blog_post", slug=slug, _external=True)
  return render_template("blog_post.html", post=post, canonical_url=canonical_url)
