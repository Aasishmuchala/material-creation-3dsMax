"""Input checks shared by forge_max (Max's Python) and forge_cli / forge_fal
(system Python). Standard library only: Max's bundled Python has no Pillow,
so the image check here reads magic bytes; the generators add a Pillow
decode on top.
"""
import os

NAME_MAX = 48                      # keeps <image dir>\<name>_maps\... < MAX_PATH
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp")
MAX_IMAGE_BYTES = 64 * 1024 * 1024

_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*", b"BM")


def safe_name(name, default="MatForge_Material"):
    """Folder-safe material name: letters/digits/underscore only (so no path
    separators, '..', control characters or Windows-reserved punctuation),
    at most NAME_MAX characters, never empty."""
    if not isinstance(name, str):
        name = ""
    cleaned = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    cleaned = cleaned[:NAME_MAX].strip("_")
    return cleaned or default


def image_problem(path):
    """None if `path` looks like a usable reference image, else a short
    user-facing reason. Checks type, existence, extension, size and the
    file's magic bytes (no decode)."""
    if not isinstance(path, str) or not path:
        return "Pick a reference image first."
    if not os.path.isfile(path):
        return "Reference image not found: %s" % path
    if os.path.splitext(path)[1].lower() not in IMAGE_EXTS:
        return ("Unsupported image type '%s' (use %s)."
                % (os.path.splitext(path)[1] or "none",
                   " ".join(IMAGE_EXTS)))
    size = os.path.getsize(path)
    if size <= 0:
        return "Reference image is empty (0 bytes)."
    if size > MAX_IMAGE_BYTES:
        return "Reference image is too large (%d MB; limit %d MB)." % (
            size // (1024 * 1024), MAX_IMAGE_BYTES // (1024 * 1024))
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError as e:
        return "Cannot read reference image: %s" % e
    if not (head.startswith(_MAGIC) or
            (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        return "Reference image is not a readable image file."
    return None


def default_out_dir(image, name):
    """<image dir>/<safe name>_maps, verified to stay inside the image dir."""
    parent = os.path.dirname(os.path.abspath(image))
    out_dir = os.path.join(parent, safe_name(name) + "_maps")
    real_parent = os.path.realpath(parent)
    real_out = os.path.realpath(out_dir)
    if (real_out == real_parent or
            os.path.commonpath([real_parent, real_out]) != real_parent):
        raise ValueError("output folder escapes the image folder")
    return out_dir
