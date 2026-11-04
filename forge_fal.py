"""MatForge fal PATINA backend — reference image -> studio-grade PBR maps.

This is the v4 AI map backend: fal-ai/patina/material/extract (default) pulls
the surface out of a photo; fal-ai/patina/material (--mode generate) is the
text(+image) generator. Both do de-light + deshadow + seamless tiling + upscale
and return basecolor/normal/roughness/metalness/height. Schema facts live in
docs/PATINA_ENDPOINT.md. It writes the SAME manifest contract as forge_cli.py (plus a
metalness map), so the Max-side builder wiring is unchanged — exactly the
swap-the-backend design the constitution's manifest contract was built for.

Needs FAL_KEY in the environment. Usage:
  py -3.12 forge_fal.py <image> --name Oak --type wood_interior \
      [--mode extract|generate] --prompt "natural light oak planks" --upscale 2 [--out DIR]
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.recipes import RECIPES  # noqa: E402
from maxplugin.inputs import default_out_dir, image_problem  # noqa: E402

ENDPOINTS = {"extract": "fal-ai/patina/material/extract",
             "generate": "fal-ai/patina/material"}

# PATINA map_type -> MatForge manifest key (both endpoints use these values;
# the first output item has no map_type and is the flat texture, skipped)
MAP_KEYS = {
    "basecolor": "albedo",
    "normal": "normal",
    "roughness": "roughness",
    "metalness": "metalness",
    "height": "height",
}

# Curated per-class prompts (deterministic — no LLM needed). PATINA expands
# these internally; the reference image supplies the rest.
PROMPTS = {
    "wood_interior": "natural oak wood plank flooring, warm honey tone, satin "
    "lacquer finish, fine straight grain, flat top-down, evenly lit, seamless "
    "PBR, photorealistic",
    "wood_exterior": "weathered exterior timber decking, greyed patina, rough "
    "sawn grain, flat top-down, evenly lit, seamless PBR, photorealistic",
    "concrete": "smooth polished concrete, subtle pitting and tonal variation, "
    "flat top-down, evenly lit, seamless PBR, photorealistic",
    "stone": "natural stone paver, granular surface, subtle colour variation, "
    "flat top-down, evenly lit, seamless PBR, photorealistic",
    "marble": "polished white Calacatta marble, subtle grey veining, flat "
    "top-down, evenly lit, seamless PBR, glossy, photorealistic",
    "metal_brushed": "brushed stainless steel, fine horizontal satin brush "
    "lines, neutral silver, flat top-down, evenly lit, seamless PBR, "
    "photorealistic",
    "metal_painted": "smooth powder-coated painted metal, matte finish, flat "
    "top-down, evenly lit, seamless PBR, photorealistic",
    "glass_clear": "clear flat glass surface, subtle imperfections, flat "
    "top-down, evenly lit, seamless PBR",
    "fabric": "woven linen upholstery fabric, soft matte weave, flat top-down, "
    "evenly lit, seamless PBR, photorealistic",
    "leather": "fine grain leather, subtle pores and creases, flat top-down, "
    "evenly lit, seamless PBR, photorealistic",
    "paint_wall": "smooth painted plaster wall, matte, subtle roller texture, "
    "flat top-down, evenly lit, seamless PBR",
    "foliage": "green leaf surface, fine veins, flat top-down, evenly lit, "
    "seamless PBR, photorealistic",
    "generic": "flat material surface, evenly lit, seamless PBR, photorealistic",
}


def fable_prompt(image_path, mclass, base_prompt):
    """Ask Fable-5 (via the omega gateway) to write a bespoke PATINA prompt by
    LOOKING at the reference photo. Falls back to `base_prompt` on any error so
    generation never depends on the gateway being up."""
    try:
        import base64
        import io

        import mfconfig
        from PIL import Image

        im = Image.open(image_path).convert("RGB")
        im.thumbnail((512, 512))          # small payload; enough to 'see' it
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        instr = (
            "You are writing ONE line of text prompt for a PBR material "
            "generator (fal PATINA) from this reference photo of a %s. "
            "Describe the material precisely — substance, colour/tone, finish "
            "(matte/satin/gloss), and characteristic surface detail — then end "
            "with 'flat top-down, evenly lit, seamless PBR, photorealistic'. "
            "Reply with ONLY the prompt line, no preamble, no quotes."
            % mclass.replace("_", " "))
        content = [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": instr}]
        out = (mfconfig.omega_message(content, max_tokens=400, timeout=35)
               or "").strip().strip('"').strip()
        if out and len(out) > 12:
            return out
    except Exception:
        pass
    return base_prompt


class JsonArgParser(argparse.ArgumentParser):
    """Argument errors still end with the one-JSON-line contract on stdout."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(json.dumps({"ok": False, "error": "bad arguments: %s" % message}))
        raise SystemExit(2)


def _image_size(path):
    """(width, height) of a fully decodable image, else raise ValueError.
    Output items may omit width/height (all optional in the schema), and a
    0-byte / HTML / truncated download must never become a map."""
    from PIL import Image
    if os.path.getsize(path) <= 0:
        raise ValueError("empty file")
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:       # verify() leaves im unusable
            im.load()
            return im.size
    except Exception as e:
        raise ValueError("not a valid image (%s)" % e)


def _progress(args, n, label):
    if args.progress:
        print("PROGRESS %d/3 %s" % (n, label), file=sys.stderr)
        sys.stderr.flush()


def main(argv=None):
    try:
        return _main(argv)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "cancelled"}))
        return 130


def _main(argv):
    ap = JsonArgParser(description="MatForge fal PATINA backend")
    ap.add_argument("image")
    ap.add_argument("--name", required=True)
    ap.add_argument("--type", required=True, choices=sorted(RECIPES),
                    dest="mclass")
    ap.add_argument("--prompt", default="",
                    help="material description to guide PATINA")
    ap.add_argument("--no-fable", action="store_true",
                    help="skip the Fable-5 vision prompt; use the class template")
    ap.add_argument("--mode", choices=sorted(ENDPOINTS), default="extract",
                    help="extract=pull the surface from the photo "
                    "(patina/material/extract); generate=text+image "
                    "(patina/material)")
    ap.add_argument("--upscale", type=int, default=2, choices=[0, 2, 4],
                    help="0=native 1K, 2=2K, 4=4K")
    ap.add_argument("--out", default=None)
    ap.add_argument("--progress", action="store_true",
                    help="print PROGRESS n/total label lines to stderr")
    a = ap.parse_args(argv)

    if not os.environ.get("FAL_KEY"):
        try:
            import mfconfig            # env -> _keys.json -> winreg -> _falkey
            k = mfconfig.get_fal_key()
            if k:
                os.environ["FAL_KEY"] = k
        except Exception:
            pass
    if not os.environ.get("FAL_KEY"):
        print(json.dumps({"ok": False, "error": "FAL_KEY not set"}))
        return 1
    if not os.path.isfile(a.image):
        print(json.dumps({"ok": False, "error": f"image not found: {a.image}"}))
        return 1
    # reject non-images / empty / oversized files BEFORE the paid upload
    problem = image_problem(a.image)
    if problem is None:
        try:
            _image_size(a.image)
        except Exception as e:
            problem = "reference image is %s" % e
    if problem:
        print(json.dumps({"ok": False, "error": problem}))
        return 1

    # everything below is inside the try so any failure emits the {"ok":false}
    # JSON contract rather than a raw traceback.
    try:
        import fal_client

        out_dir = a.out or default_out_dir(a.image, a.name)
        os.makedirs(out_dir, exist_ok=True)

        _progress(a, 1, "Uploading the photo")
        url = fal_client.upload_file(a.image)
        base_prompt = a.prompt or PROMPTS.get(a.mclass, PROMPTS["generic"])
        if a.prompt or a.no_fable:
            prompt = base_prompt
        else:                              # Fable-5 looks at the photo
            prompt = fable_prompt(a.image, a.mclass, base_prompt)
        _progress(a, 2, "Waiting for the AI")
        res = fal_client.subscribe(
            ENDPOINTS[a.mode],
            arguments={"image_url": url, "prompt": prompt,
                       "upscale_factor": a.upscale},
            with_logs=False)

        maps, sizes, warnings = {}, {}, []
        announced = False
        for im in res.get("images", []):
            mt = im.get("map_type")
            if mt in MAP_KEYS:
                key = MAP_KEYS[mt]
                dest = os.path.join(out_dir, key + ".png")
                tmp = dest + ".part"       # atomic: download then rename
                if not announced:
                    announced = True
                    _progress(a, 3, "Downloading the maps")
                try:
                    urllib.request.urlretrieve(im["url"], tmp)
                    try:
                        size = _image_size(tmp)
                    except ValueError as e:
                        raise RuntimeError("downloaded %s map is %s" % (mt, e))
                    os.replace(tmp, dest)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                maps[key] = os.path.abspath(dest)
                sizes[key] = size
                claimed = im.get("width")
                if claimed and claimed != size[0]:
                    warnings.append("%s: fal reported %spx, file is %dpx"
                                    % (mt, claimed, size[0]))
        if "albedo" not in maps:
            raise RuntimeError("PATINA returned no basecolor map")
        res_px = sizes["albedo"][0]       # res = the albedo's real width
        odd = sorted(k for k, sz in sizes.items() if sz != sizes["albedo"])
        if odd:
            warnings.append("map sizes differ from albedo %dx%d: %s" % (
                sizes["albedo"][0], sizes["albedo"][1],
                ", ".join("%s %dx%d" % (k, sizes[k][0], sizes[k][1])
                          for k in odd)))

        manifest = {"schema": 1, "name": a.name, "class": a.mclass,
                    "res": f"{res_px}px", "maps": maps, "source": "fal-patina-" + a.mode,
                    "input_prompt": prompt,
                    "patina_prompt": res.get("prompt", ""), "warnings": warnings}
        mp = os.path.join(out_dir, "manifest.json")
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1

    print(json.dumps({"ok": True, "manifest": os.path.abspath(mp),
                      "maps": sorted(maps), "res": f"{res_px}px",
                      "warnings": warnings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
