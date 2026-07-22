"""Probe fal-ai/patina/material — upload a reference, run it, dump the result
structure so we can map its outputs to the MatForge manifest."""
import json
import os
import sys

import fal_client

img = r"C:\Users\aasis\matforge\sample_maps\fal_wood.jpg"
if not os.environ.get("FAL_KEY"):
    print("NO FAL_KEY"); sys.exit(1)

print("uploading reference...")
url = fal_client.upload_file(img)
print("uploaded:", url)

for model, args in [
    ("fal-ai/patina/material",
     {"image_url": url,
      "prompt": "natural light oak wood planks, flat surface, PBR material",
      "upscale_factor": 0}),
]:
    print("\n=== calling", model, "===")
    try:
        res = fal_client.subscribe(model, arguments=args, with_logs=False)
        print("RESULT KEYS:", list(res.keys()))
        print(json.dumps(res, indent=2)[:2500])
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:800])
