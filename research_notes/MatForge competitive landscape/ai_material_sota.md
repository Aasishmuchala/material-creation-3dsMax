# AI and computational methods for photo to PBR/SVBRDF materials (2023 to Nov 2026)

Scope note: about 17 tool calls of research. Several named items (ControlMat, Material Palette, MatGPT-style, polarisation capture, Substance Sampler internals, IntrinsicAnything/RGB-X licences, 2026 papers) were NOT resolved and are listed under Gaps. Nothing marked "unverified" should be quoted as fact.

## 1. Single-image SVBRDF estimation and de-lighting: best methods, capabilities, licences

### Takeaway
The strongest openly measurable single-image estimator is Ubisoft CHORD (SIGGRAPH Asia 2025), but its weights are research-only and gated, so it cannot be shipped in a commercial plugin. Commercially usable routes found are: the fal PATINA API (already in MatForge, "Commercial use" label), Marigold-IID (OpenRAIL++-M, needs legal read), and the NVIDIA Cosmos DiffusionRenderer (NVIDIA Open Model License, stated commercial use). Adobe's Image to Material is application-only, not an embeddable model.

### Cited Findings
- CHORD ("Chain of Rendering Decomposition"), Ying, Rong, Wang, Xu; SIGGRAPH Asia 2025; arXiv 2509.09952. Two-stage: fine-tuned diffusion generates tileable shaded textures, then a chained single-step image-conditional diffusion estimates SVBRDF channels one at a time. Supports text-to-material, image-to-material, structure-guided generation and editing. — [arXiv abs](https://arxiv.org/abs/2509.09952)
- CHORD licence is "Ubisoft Machine Learning License (Research-Only - Copyleft)"; HF repo is gated (must accept terms). Trained on MatSynth. Code at github.com/ubisoft/ubisoft-laforge-chord (Python 3.12, PyTorch cu128), ComfyUI nodes at ubisoft/ComfyUI-Chord. Full LICENSE text not read; "research-only" strongly implies no commercial use. — [HF model card](https://huggingface.co/Ubisoft/ubisoft-laforge-chord), [GitHub](https://github.com/ubisoft/ubisoft-laforge-chord), [Comfy blog](https://blog.comfy.org/p/ubisoft-open-sources-the-chord-model)
- CHORD benchmark (PSNR higher better / LPIPS lower better, 1k res, 9 point/directional relight lights). MatSynth test split (89 materials, 356 images): basecolor 28.78/0.269 vs RGB-X 25.79/0.313; normal 26.65/0.353 vs 25.67/0.361; roughness 19.31/0.532 vs RGB-X 18.11/0.512 (CHORD higher PSNR, worse LPIPS); metalness 71.93/0.089 vs 61.40/0.102. Curated Substance test set (250 materials): basecolor 29.05/0.269, normal 23.32/0.334, roughness 17.48/0.550, metalness 77.67/0.064, height 23.36/0.470, relit 22.94/0.309. — [CHORD HTML paper](https://arxiv.org/html/2509.09952v1)
- Same table, baselines on the Substance set (basecolor PSNR/LPIPS): Material Palette 16.04/0.384; SurfaceNet 24.60/0.326; MatFusion 25.35/0.347; RGB-X 25.72/0.317. Roughness is the weakest channel for every method (PSNR 14 to 17.5). — [CHORD HTML paper](https://arxiv.org/html/2509.09952v1)
- Inference time on RTX A6000: SurfaceNet 0.6 s, MatFusion 46.4 s, RGB-X 23.6 s, CHORD 2.1 s (about 11x faster than RGB-X). CHORD 1.4B params, trained on 512x512 crops, evaluated at 1k. — [CHORD HTML paper](https://arxiv.org/html/2509.09952v1)
- Caveat: those numbers are self-reported by the CHORD authors on their own curated Substance test set; no independent replication found.
- MaterialPicker, Adobe Research + Zhejiang Univ.; arXiv 2412.03225; SIGGRAPH 2025. Diffusion Transformer finetuned from a video generator, each material map treated as a video frame; generates from image crop (handles angled, distorted, occluded photos), text, or both. Reported 800K text-material pairs; a secondary summary claims about 12 s vs 3 min for prior methods (unverified). Code/weights status not confirmed. — [Adobe Research page](https://research.adobe.com/publication/materialpicker-multi-modal-dit-based-material-generation), [arXiv](https://arxiv.org/abs/2412.03225)
- MatFusion, Sartor and Peers, SIGGRAPH Asia 2023, arXiv 2406.06539. Unconditional diffusion backbone trained on 312,165 synthetic SVBRDFs, conditional models for flash, uncontrolled lighting or flash/no-flash pairs; multiple candidate outputs per photo. Slow (46.4 s per CHORD table). — [arXiv PDF](https://arxiv.org/pdf/2406.06539)
- StableMaterials (Vecchio, arXiv 2406.09293, v3 Jan 2025): HF model page lists licence openrail; semi-supervised diffusion for material generation, public via gvecchio.com/stablematerials. MatFuse repo (giuvecchio/matfuse) built on CompVis latent diffusion; licence text not seen. ControlMat: a HF discussion asks when it will be released, so likely no public weights (unverified). — [StableMaterials arXiv](https://arxiv.org/html/2406.09293v2), [HF discussions](https://huggingface.co/gvecchio/StableMaterials/discussions), [MatFuse mirror](https://gh.r-mj.com/giuvecchio/matfuse)
- MatSynth dataset: over 4,000 tileable 4K PBR materials (3,980 train, 89 test, 4,069 unique), 433 GB, mostly CC0 (AmbientCG, CGBookCase, PolyHaven, ShareTextures, TextureCan), a limited set CC-BY; per-material licence in metadata. Commercial training/benchmark use is permitted for CC0 subset; CC-BY needs attribution. — [HF dataset](https://huggingface.co/datasets/gvecchio/MatSynth)
- Marigold IID (ETH, arXiv 2505.09358): Appearance model outputs albedo, roughness, metallicity; Lighting model outputs albedo, diffuse shading, non-diffuse residual. HF card for appearance v1-1 lists CreativeML Open RAIL++-M (fine-tuned from Stable Diffusion 2), which allows commercial use with use-based restrictions. — [Marigold arXiv](https://arxiv.org/pdf/2505.09358), [HF card](https://huggingface.co/prs-eth/marigold-iid-appearance-v1-1)
- RGB-X (Zeng et al., SIGGRAPH 2024): diffusion estimates albedo, roughness, metallicity, lighting and the reverse X to RGB. Licence not found in searches. IntrinsicAnything: diffusion prior for material recovery under unknown illumination; code/licence not confirmed. — [RGB-X via Marigold search results](https://arxiv.org/pdf/2505.09358) (secondary only)
- DiffusionRenderer (NVIDIA, CVPR 2025, arXiv 2501.18590): video inverse+forward renderer. Original repo: Nvidia Source Code License, with the SVD-based model under Stability AI Community License. Cosmos-based variant (HF zianw/Diffusion_Renderer_Inverse_Cosmos_7B) under NVIDIA Open Model License, card says commercial use allowed. 7B model, video-oriented, heavy for a plugin; outputs G-buffers (albedo, normals, roughness, metallic), not tileable maps. — [GitHub](https://github.com/nv-tlabs/diffusion-renderer), [HF Cosmos card](https://huggingface.co/zianw/Diffusion_Renderer_Inverse_Cosmos_7B), [NVIDIA page](https://research.nvidia.com/labs/toronto-ai/publication/2025_cvpr_diffusionrenderer)
- DualMat (arXiv 2508.05060, 2025): dual-path diffusion, albedo path and metallic/roughness path; venue and code not verified. — [Pith](https://pith.science/paper/2508.05060)
- Adobe Substance 3D Sampler Image to Material (AI Powered), shipped in Sampler 4.2 (5 Sep 2023): outputs base colour, roughness, normal, displacement, metallic from one image; removes shadows/highlights from albedo; user picks material category; slow at high res. Available only inside Sampler/Capture (subscription), not as an embeddable model or public API found. — [80.lv](https://80.lv/articles/adobe-releases-substance-3d-sampler-4-2), [Adobe Research blog](https://research.adobe.com/news/behind-the-tech-image-to-material-in-adobe-substance-3d-sampler-and-adobe-capture), [Adobe help](https://helpx.adobe.com/substance-3d-sampler/filters/tools/image-to-material.html)
- fal PATINA family: endpoints fal-ai/patina, fal-ai/patina/material, fal-ai/patina/material/extract. fal-ai/patina/material is TEXT-to-PBR (optional image_url for img2img/inpaint), up to 8K, tiling modes, outputs basecolor, normal, roughness, metalness, height, 1 to 8 steps. Pricing $0.01 base + $0.02/MP + $0.01/MP per map; 1024x1024 with all five maps $0.08; 2048 with 4x upscale $0.61. Labelled "Commercial use", terms not shown. A third-party directory says backbone is a modified FLUX.2 [klein] (single secondary source, unverified). WaveSpeedAI hosts PATINA material at $0.48 per generation (different provider). — [fal model page](https://fal.ai/models/fal-ai/patina/material), [price aggregator](https://pricepertoken.com/image/model/fal-ai-patina)

### Inferences
- CHORD is the quality yardstick but is not shippable; its published numbers are the best available baseline to benchmark MatForge/PATINA outputs against (run both on MatSynth test).
- fal-ai/patina/material/extract is the endpoint that matches MatForge's photo-to-maps use; verify which endpoint MatForge calls, since /material is text-led.
- Roughness and metalness remain the weak outputs of every model (low PSNR), consistent with keeping a user-editable roughness/metalness stage in the plugin.
- For local/offline commercial inference, Marigold-IID appearance (OpenRAIL++) is the most plausible candidate but produces non-tileable, per-pixel maps at base resolution without height; needs legal review of RAIL use restrictions.

### Gaps
- Licence text of CHORD LICENSE, RGB-X, IntrinsicAnything, MaterialPicker, MatFusion not read.
- Material Palette and ControlMat specifics (venue, code, licence) not found.
- No 2026 (CVPR/SIGGRAPH 2026) single-image material paper was confirmed; searches returned only 2025 items. Newest-first coverage for 2026 is incomplete.
- Substance Sampler model architecture and any Adobe API/Firefly material endpoint: not found.
- VRAM requirements for CHORD, Marigold, PATINA not stated in sources read.

## 2. Multi-view, flash/no-flash, phone capture, inverse rendering from video, polarisation

### Takeaway
Flash/no-flash and phone capture is a mature but older line (2015 to 2022) now largely absorbed into diffusion models (MatFusion conditions on flash or flash/no-flash). Relightable 3DGS inverse rendering exists in 2025 but targets objects/scenes, not tileable surface materials. Polarisation capture: nothing found.

### Cited Findings
- Aittala et al. two-shot flash/no-flash SVBRDF (2015) works on handheld JPEG phone images of planar stationary samples; Deschaintre et al. 2018 single flash image; multi-image uncalibrated handheld network follows; MaterialGAN captures SVBRDF from few mobile flash photos; ICCP 2022 smartphone flash/no-flash RGB-D inverse rendering. — [search-surfaced papers: MatFusion PDF](https://arxiv.org/pdf/2406.06539), [Two-shot SVBRDF](https://reality.tf.fau.de/projects/two-shot-svbrdf/two-shot-svbrdf.pdf), [ICCP 2022](https://vclab.kaist.ac.kr/iccp2022/iccp2022-paper.pdf)
- MatFusion conditional models accept flash, uncontrolled lighting, or flash/no-flash input and can sample multiple estimates. — [arXiv PDF](https://arxiv.org/pdf/2406.06539)
- 2025 relightable Gaussian splatting: Discretized SDF for Relightable Assets (ICCV 2025), RTR-GS (arXiv 2507.07733), SVG-IR (arXiv 2504.06815), Phys3DGS (arXiv 2409.10335, 2024), MatSpray (casual multi-view photos plus 2D diffusion material priors lifted onto 3DGS; about 3.5x faster than IRGS per secondary summary; no arXiv ID or venue found). — [ICCV 2025 listing](https://mlanthology.org/iccv/2025/zhu2025iccv-gaussian/), [RTR-GS](https://www.emergentmind.com/topics/rtr-gs), [SVG-IR](https://arxiv.org/abs/2504.06815v1), [MatSpray summary](https://api.emergentmind.com/topics/matspray)
- Common limits noted: geometry/material/lighting ambiguity and discrete Gaussians. — same sources.
- A 2025 study (arXiv 2512.13950) evaluates single-image SVBRDF predictors (Kocsis et al., RGB-X, GenPercept) inside generative multiview pipelines for 3D scene appearance. — [ar5iv](https://ar5iv.labs.arxiv.org/html/2512.13950), [review](https://www.themoonlight.io/review/an-evaluation-of-svbrdf-prediction-from-generative-image-models-for-appearance-modeling-of-3d-scenes)

### Inferences
- A practical MatForge upgrade path is an optional "second photo with flash" input via a flash-conditioned model, but no commercially licensed, downloadable flash-conditioned model was identified.
- 3DGS relighting is overkill for flat-surface materials; relevant mainly for object capture.

### Gaps
- No 2025 to 2026 dedicated flash/no-flash or phone multi-light SVBRDF paper with released weights found.
- Polarisation capture: no sources found.
- Quantitative benchmarks for the 3DGS methods not collected.

## 3. Text-to-material and procedural graph generation

### Takeaway
Procedural-graph synthesis has moved from MatFormer (2022) to VLM-based program synthesis (VLMaterial ICLR 2025, MultiMat ICLR 2026). These output Substance/Blender graphs, which are editable and resolution-independent, but release of code/weights is unconfirmed, and they do not map directly to VRayMtl/Corona maps without baking.

### Cited Findings
- MultiMat (Adobe Research, arXiv 2509.22151, ICLR 2026): Qwen2.5-VL 7B based; shows intermediate graph visualisations and uses constrained tree search with per-node validation; transpiler between Substance Designer format and compact LM representation. Unconditional KID 2.365 (Graph) vs VLMaterial 14.155; conditional DreamSim 36.6 vs 31.3, CLIP 67.9 vs 65.7; with parameter optimisation DreamSim 40.4. Trained on Substance 3D Assets repository (Community Assets excluded for licensing). Code/weights/licence not stated. — [arXiv HTML](https://arxiv.org/html/2509.22151v2)
- VLMaterial (Li et al., ICLR 2025, arXiv 2501.18623): VLM generates Blender procedural material code from images; over 550,000 Blender procedural material dataset. — [search result summary](https://www.themoonlight.io/review/vlmaterial-procedural-material-generation-with-large-vision-language-models)
- MatFormer (Guerrero et al., 2022, Substance Designer graph transformer) and Hu et al. 2023 (arXiv 2304.13172) multimodal CLIP-conditioned node graph generation. — [arXiv 2304.13172](https://ar5iv.labs.arxiv.org/html/2304.13172)
- fal PATINA material and CHORD both support text-to-tileable-material via diffusion (see section 1).

### Inferences
- Procedural output is attractive for MatForge's native-material goal but needs a graph evaluator (Substance engine or Blender), adding a heavy dependency; baked maps from PATINA/CHORD fit the current architecture better.

### Gaps
- MatGPT-style LLM graph generation: no source found under that name.
- Tileable texture diffusion beyond CHORD/PATINA/StableMaterials not researched.
- Code release and licences for MultiMat/VLMaterial unconfirmed.

## 4. Weights, commercial licences, API-only options, cost and speed

### Takeaway
Only PATINA (fal), Adobe Sampler and WaveSpeed-hosted PATINA are confirmed products; open weights are mostly research-only or ambiguous. Speed: single-step CHORD about 2 s on an A6000; multi-step diffusion (MatFusion, RGB-X) 23 to 46 s.

### Cited Findings
- CHORD: downloadable but research-only, gated. — [HF](https://huggingface.co/Ubisoft/ubisoft-laforge-chord)
- StableMaterials: openrail on HF. — [HF discussions](https://huggingface.co/gvecchio/StableMaterials/discussions)
- Marigold-IID appearance v1-1: CreativeML Open RAIL++-M. — [HF](https://huggingface.co/prs-eth/marigold-iid-appearance-v1-1)
- DiffusionRenderer Cosmos: NVIDIA Open Model License, card states commercial use; original repo NVIDIA Source Code License + Stability Community License. — [HF](https://huggingface.co/zianw/Diffusion_Renderer_Inverse_Cosmos_7B), [GitHub](https://github.com/nv-tlabs/diffusion-renderer)
- fal PATINA: $0.08 for 1k x 1k five maps; $0.61 for 2k with 4x upscale; WaveSpeedAI $0.48 per generation. — [fal](https://fal.ai/models/fal-ai/patina/material), [pricepertoken](https://pricepertoken.com/image/model/fal-ai-patina)
- Consumer tools listed (ArmorLab, Materialize, Substance Sampler) without verified pricing or licences. — [3daistudio blog](https://www.3daistudio.com/blog/best-ai-texture-and-pbr-generators-2026) (low-reliability marketing blog)

### Inferences
- Run-cost for PATINA is cents per material, so API cost is negligible versus engineering to self-host; self-hosting only matters for offline/privacy requirements or vendor risk.
- Vendor-risk mitigation: keep a fallback local model with a clean commercial licence (Marigold-IID or a model MatForge trains on MatSynth's CC0 subset).

### Gaps
- Replicate-hosted material models and Adobe API availability: not searched.
- Per-image cost of a self-hosted GPU deployment not computed.

## 5. Quality metrics and benchmarks

### Takeaway
The field reports per-map PSNR and LPIPS on MatSynth test and relit-render PSNR/LPIPS under fixed lights; procedural work uses KID, DreamSim, CLIP similarity and expert preference. No standard perceptual benchmark on real phone photos exists in sources found.

### Cited Findings
- CHORD protocol: MatSynth test (89 materials, 356 images) plus 250-material Substance set at 1k; per-map PSNR/LPIPS and relight under nine lights. Best-reported scores listed in section 1. — [CHORD HTML](https://arxiv.org/html/2509.09952v1)
- MultiMat uses KID, ROUGE-L (memorisation), node error ratio, DreamSim, CLIP, style loss and human study. — [arXiv HTML](https://arxiv.org/html/2509.22151v2)
- MatSynth test split is 89 materials, 4K tileable. — [HF dataset](https://huggingface.co/datasets/gvecchio/MatSynth)

### Inferences
- Because test sets are synthetic crops, scores overstate real-photo performance; MatForge should build a small in-house set of real photo + scanned-ground-truth pairs and report relit LPIPS under V-Ray/Corona renders.

### Gaps
- Rendering-error (RMSE/FLIP) numbers for MaterialPicker, StableMaterials, Marigold not collected.
- No independent third-party benchmark of real-photo performance found.
