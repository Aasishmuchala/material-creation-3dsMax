"""Generate several MatForge PATINA material sets in PARALLEL at 4K.
Submits all fal jobs first (they process concurrently on fal's side), then
collects + downloads each. Needs FAL_KEY.
"""
import json
import os
import sys
import urllib.request

import fal_client

MAP_KEYS = {"basecolor": "albedo", "normal": "normal", "roughness": "roughness",
            "metalness": "metalness", "height": "height"}
SM = r"C:\Users\aasis\matforge\sample_maps"

JOBS = [
    ("fal_wood.jpg", "Wood4K", "wood_interior",
     "natural European oak plank flooring, warm honey tone, satin lacquer "
     "finish, fine straight grain, flat top-down, evenly lit, seamless PBR, "
     "photorealistic"),
    ("real_marble.jpg", "Marble4K", "marble",
     "polished white Calacatta marble slab, subtle grey and gold veining, "
     "flat top-down, evenly lit, seamless PBR, glossy, photorealistic"),
    ("real_metal.jpg", "Metal4K", "metal_brushed",
     "brushed stainless steel, fine horizontal satin brush lines, flat "
     "top-down, evenly lit, seamless PBR, photorealistic"),
]


def main():
    if not os.environ.get("FAL_KEY"):
        print("NO FAL_KEY"); return 1
    handles = []
    for img, name, cls, prompt in JOBS:
        path = os.path.join(SM, img)
        url = fal_client.upload_file(path)
        h = fal_client.submit("fal-ai/patina/material",
                              arguments={"image_url": url, "prompt": prompt,
                                         "upscale_factor": 4})
        handles.append((name, cls, h))
        print("submitted", name)

    for name, cls, h in handles:
        try:
            res = h.get()
            out_dir = os.path.join(SM, name + "_maps")
            os.makedirs(out_dir, exist_ok=True)
            maps, px = {}, None
            for im in res.get("images", []):
                mt = im.get("map_type")
                if mt in MAP_KEYS:
                    dest = os.path.join(out_dir, MAP_KEYS[mt] + ".png")
                    urllib.request.urlretrieve(im["url"], dest)
                    maps[MAP_KEYS[mt]] = os.path.abspath(dest)
                    px = im.get("width", px)
            manifest = {"schema": 1, "name": name, "class": cls,
                        "res": f"{px}px", "maps": maps, "source": "fal-patina"}
            with open(os.path.join(out_dir, "manifest.json"), "w",
                      encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            print(json.dumps({"name": name, "ok": True, "res": f"{px}px",
                              "maps": sorted(maps)}))
        except Exception as e:
            print(json.dumps({"name": name, "ok": False, "error": str(e)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
