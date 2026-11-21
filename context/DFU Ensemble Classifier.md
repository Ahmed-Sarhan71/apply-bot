# DFU Ensemble Classifier

<a href="https://dfu-ensemble-classifier-khh2c3a8946wqh32efkn4h.streamlit.app/" target="_blank"><img src="https://img.shields.io/badge/Live%20Demo-Streamlit-FF4B4B?logo=streamlit" alt="Streamlit App"></a>

Deep learning system for classifying **Infection** and **Ischaemia** in Diabetic Foot Ulcer images using an ensemble of 5 ResNet18 models. Provides wound type (1–4) with suggestive treatment recommendations.

**Best Results:** Infection F1=0.855, Ischaemia F1=0.824

---

## Overview

Chronic wounds affect ~6.5 million patients in the US alone. Diabetic Foot Ulcers are among the most serious — 56% become infected, 20% lead to amputation. Patients with DFU and critical ischaemia face ~40% three-year amputation rate.

Current manual wound assessment is time-intensive and inconsistent. This project automates classification using deep learning:

- **Infection** — bacterial invasion detected via visual signs (redness, purulent discharge, inflammation)
- **Ischaemia** — inadequate blood supply (poor reperfusion, tissue necrosis, gangrenous toes)

ResNet18 fine-tuned on DFU dataset (Goyal et al. 2019) with patient-ID-disjoint splits. Five models ensembled at inference. Decision thresholds tuned per task to maximise F1.

---

## Features

- **Dual classification** — predicts both infection and ischaemia from one image
- **Wound typing** — 4-type matrix combining both predictions
- **Treatment guidance** — dressing material, antibiotic, and surgical recommendations per type
- **Test samples** — 40 pre-labelled images (10 per class) with ground truth comparison
- **Upload or select** — use your own images or browse test samples

---

## Wound Type Matrix

| Type | Infection | Ischaemia |
|:----:|:---------:|:---------:|
| 1 | Positive | Positive |
| 2 | Positive | Negative |
| 3 | Negative | Positive |
| 4 | Negative | Negative |

## Suggestive Treatment (Prognosis)

| Type | Wound Description | Dressing Material | Antibiotic | Surgical Procedure |
|:----:|:-----------------|:------------------|:-----------|:-------------------|
| 1 | Infected – Ischaemic wound | Foam, Alginate, Hydrofiber, Polymeric membrane | May or may not based on underlying cause | Find & treat underlying cause if necessary |
| 2 | Infected – Non Ischaemic wound | Tulle, Hydrogel, Hydrocolloid, Silver dressing | Yes | Debridement may be needed |
| 3 | Non Infected – Ischaemic wound | Alginate, Foam, Silver | Yes | Debridement may be needed |
| 4 | Non Infected – Non Ischaemic wound | All types except silver, charcoal, special advanced | No | Ready for secondary wound closure. If small, continue dressing till heals |

---

## Results

Threshold tuning was the highest-ROI change — no retraining, just moving the decision boundary. Ensemble further improved all metrics.

| Exp | Change | Infection F1 | Ischaemia F1 |
|-----|--------|:------------:|:------------:|
| 1 | Baseline (random split, t=0.5) | 0.793 | 0.534 |
| 2 | Patient-ID split + threshold tuning ✓ | 0.840 | 0.754 |
| 3 | Freeze backbone ❌ | 0.819 | 0.727 |
| 4 | Dropout(0.5) ❌ | 0.803 | 0.701 |
| 5 | Focal Loss (γ=2.0) ❌ | 0.785 | 0.659 |
| 6 | EfficientNet-B0 ❌ | 0.819 | 0.667 |
| **7** | **5-model ensemble (seeds 42–46) ★** | **0.855** | **0.824** |

### Best Configuration — Exp7

| Task | Accuracy | Precision | Recall | F1 | AUC | Threshold |
|------|:--------:|:---------:|:------:|:--:|:---:|:---------:|
| Infection | 0.813 | 0.766 | **0.968** | **0.855** | **0.901** | ≥ 0.55 |
| Ischaemia | 0.945 | 0.778 | **0.875** | **0.824** | **0.969** | ≥ 0.60 |

Only 4 missed infections out of 125 and 4 missed ischaemia out of 32.

---

## How It Works

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backbone | ResNet18 (11M params) | EfficientNet-B0 too small; full fine-tune needed for wound features |
| Ensemble | 5 models (seeds 42–46) | Smooths overfitting; recall +2.4%, AUC +4.1% |
| Threshold | Tuned per task (0.55 / 0.60) | Ischaemia 6:1 imbalance suppresses probabilities below 0.5 |
| Loss | CrossEntropy (not Focal) | Focal + balanced sampler over-corrected, flooded FP |
| Regularization | None (no Dropout) | fc layer only 1,026 params; dropout removed too many connections |
| Split | Patient-ID disjoint | Prevents patient-level leakage between train/test |

---

## Dataset & Limitations

The dataset (Goyal et al. 2019) originally contains **5,890 augmented images for infection** and **9,870 for ischaemia**. After removing rotated and masked variants and deduplicating by patient ID, only **1,447 unique images per task** remain.

Key issues:

- **Low data volume** — 1,012 train images per task is far from ideal for 11M-parameter models
- **Poor image quality** — many images are low-resolution, poorly lit, or obstructed
- **Subtle visual differences** — infected vs non-infected and ischaemic vs non-ischaemic wounds often look nearly identical, making classification difficult even for human experts
- **Clinical gold standard requires tests** — diagnosing infection requires blood tests or wound cultures; ischaemia requires Doppler ultrasound or ABPI. Visual inspection alone is insufficient

In medical screening, **false negatives are far more dangerous than false positives** — a missed infection or ischaemia can lead to amputation or sepsis. Models were saved by **highest recall** during training.

**Best recall:** Infection 0.968 (4 missed out of 125), Ischaemia 0.875 (4 missed out of 32).

> ⚠️ **Academic proof-of-concept only.** Not for clinical use. Needs larger datasets, multi-modal inputs, and clinical validation before deployment.

---

## Usage

### Try Live

<a href="https://dfu-ensemble-classifier-khh2c3a8946wqh32efkn4h.streamlit.app/" target="_blank">https://dfu-ensemble-classifier-khh2c3a8946wqh32efkn4h.streamlit.app/</a>

![App Screenshot](preview_image.png)

### Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Upload a foot ulcer image or pick from **40 pre-labelled test samples**. App shows:

- Infection / Ischaemia prediction with confidence
- Wound type (1–4) with description
- Suggestive treatment (dressing, antibiotic, surgical)
- ✅/❌ ground truth comparison for test samples

### Programmatic Inference

```python
from PIL import Image
import torch, torch.nn as nn
from torchvision import transforms, models
import numpy as np

val_tf = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

img = val_tf(Image.open("image.jpg").convert("RGB")).unsqueeze(0)
thresh = {"infection": 0.55, "ischaemia": 0.60}
seeds = [42, 43, 44, 45, 46]

for task in ["infection", "ischaemia"]:
    probs = []
    for seed in seeds:
        m = models.resnet18()
        m.fc = nn.Linear(512, 2)
        m.load_state_dict(torch.load(f"models/{task}_seed{seed}_fp16.pt", map_location="cpu"))
        m.eval()
        with torch.no_grad():
            probs.append(torch.softmax(m(img), 1)[0, 1].item())
    avg = np.mean(probs)
    pred = "Positive" if avg >= thresh[task] else "Negative"
    print(f"{task}: {pred} ({avg:.3f})")
```

### Wound Type Logic

```python
inf_pos = "Positive"   # from model
isch_pos = "Positive"
if inf_pos and isch_pos:     wt = 1
if inf_pos and not isch_pos: wt = 2
if not inf_pos and isch_pos: wt = 3
if not inf_pos and not isch_pos: wt = 4
```

---

## Repository Contents

```
├── app.py                       # Streamlit web app
├── models/                      # Pre-trained fp16 weights (5 seeds × 2 tasks)
│   ├── infection_seed{42..46}_fp16.pt
│   └── ischaemia_seed{42..46}_fp16.pt
├── Test Images/                 # 40 labelled test samples (10 per class)
│   ├── infection negative/
│   ├── infection positive/
│   ├── ischaemia negative/
│   └── ischaemia positive/
├── requirements.txt
├── LICENSE
└── README.md
```

Models tracked via [Git LFS](https://git-lfs.com). Clone with `git lfs pull` after checkout.

---

## Requirements

- Python ≥ 3.9
- PyTorch ≥ 2.0 & torchvision ≥ 0.15
- scikit-learn ≥ 1.2
- Pillow ≥ 10.0, numpy ≥ 1.24
- streamlit ≥ 1.28

---

## License

[MIT](LICENSE)

---

## Citation

```
Goyal, M., Reeves, N.D., Rajbhandari, S., Ahmad, N., Wang, C., Yap, M.H. (2019).
Recognition of Ischaemia and Infection in Diabetic Foot Ulcers: Dataset and Techniques.
Computers in Biology and Medicine, 117, 103616.
```
