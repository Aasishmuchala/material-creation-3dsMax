"""MatForge fal PATINA backend — reference image -> studio-grade PBR maps.

This is the v4 AI map backend: fal-ai/patina/material does real de-light +
deshadow + seamless tiling + upscale and returns basecolor/normal/roughness/
metalness/height. It writes the SAME manifest contract as forge_cli.py (plus a
metalness map), so the Max-side builder wiring is unchanged — exactly the
swap-the-backend design the constitution's manifest contract was built for.

Needs FAL_KEY in the environment. Usage:
  py -3.12 forge_fal.py <image> --name Oak --type wood_interior \
      --prompt "natural light oak planks" --upscale 2 [--out DIR]
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.recipes import RECIPES  # noqa: E402

# PATINA map_type -> MatForge manifest key
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="MatForge fal PATINA backend")
    ap.add_argument("image")
    ap.add_argument("--name", required=True)
    ap.add_argument("--type", required=True, choices=sorted(RECIPES),
                    dest="mclass")
    ap.add_argument("--prompt", default="",
                    help="material description to guide PATINA")
    ap.add_argument("--no-fable", action="store_true",
                    help="skip the Fable-5 vision prompt; use the class template")
    ap.add_argument("--upscale", type=int, default=2, choices=[0, 2, 4],
                    help="0=native 1K, 2=2K, 4=4K")
    ap.add_argument("--out", default=None)
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

    # everything below is inside the try so any failure emits the {"ok":false}
    # JSON contract rather than a raw traceback.
    try:
        import fal_client

        out_dir = a.out or os.path.join(
            os.path.dirname(os.path.abspath(a.image)), f"{a.name}_maps")
        os.makedirs(out_dir, exist_ok=True)

        url = fal_client.upload_file(a.image)
        base_prompt = a.prompt or PROMPTS.get(a.mclass, PROMPTS["generic"])
        if a.prompt or a.no_fable:
            prompt = base_prompt
        else:                              # Fable-5 looks at the photo
            prompt = fable_prompt(a.image, a.mclass, base_prompt)
        res = fal_client.subscribe(
            "fal-ai/patina/material",
            arguments={"image_url": url, "prompt": prompt,
                       "upscale_factor": a.upscale},
            with_logs=False)

        maps, res_px = {}, None
        for im in res.get("images", []):
            mt = im.get("map_type")
            if mt in MAP_KEYS:
                dest = os.path.join(out_dir, MAP_KEYS[mt] + ".png")
                tmp = dest + ".part"       # atomic: download then rename
                urllib.request.urlretrieve(im["url"], tmp)
                os.replace(tmp, dest)
                maps[MAP_KEYS[mt]] = os.path.abspath(dest)
                res_px = im.get("width", res_px)
        if "albedo" not in maps:
            raise RuntimeError("PATINA returned no basecolor map")

        manifest = {"schema": 1, "name": a.name, "class": a.mclass,
                    "res": f"{res_px}px", "maps": maps, "source": "fal-patina",
                    "input_prompt": prompt,
                    "patina_prompt": res.get("prompt", ""), "warnings": []}
        mp = os.path.join(out_dir, "manifest.json")
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1

    print(json.dumps({"ok": True, "manifest": os.path.abspath(mp),
                      "maps": sorted(maps), "res": f"{res_px}px"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
