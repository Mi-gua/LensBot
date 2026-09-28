# LensBot 结果摘要

- Generated at: 2026-09-22T16:30:20
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100`

## 设计要求

T06：设计一支可见光 RGB 广角成像镜头，用于无限远目标。要求有效焦距为 28 mm，对角全视场为 75°，F 数为 4.0，对应约 43.0 mm 的像面直径。初始后焦距设为 18 mm，初始总厚度设为 60 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 28 mm |
| F 数 | 4 |
| 全视场 | 75 deg |
| 初始后焦距 BFL | 18 mm |
| 初始总长 TTL | 60 mm |

## 结论

Agent 判断：暂无法判断。Delivered prescription candidate-002 (seed_117 F_014 all-spherical 6-element wide-angle inverse-telephoto, 11 surfaces, internal stop) is the best contract match of the three refinement blocks: measured EFL 28.50 mm (target 28, +1.78%), sensor-implied FOV 74.04 deg (target 75, -1.28%), working F/# 3.93 (target 4.0, -1.66%), TTL 59.99 mm with positive minimum vertex spacing 1.75 mm and nominal spot/MTF quality (center RMS 24.5 um, max 40.4 um). Verdict is uncertain because the contract states exact targets with no tolerance, so all three are flagged unknown_tolerance and pass_eligible=false and compliance can be neither confirmed nor denied; edge evidence is also bounded (GeoLens ray sampling only reached ~66 deg full field vs the 75 deg target) and the ~60% edge-distortion reading with a 100% valid-ray fraction is internally implausible (that mapping would exceed the sensor), so it is treated as low-confidence rather than a validated defect.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 28 mm | 29.056 mm | +3.77% | Zemax（另有 DeepLens） |
| 工作 F 数 | 4 | 4.0315 | +0.79% | Zemax（另有 DeepLens） |
| 全视场 | 75 deg | 73.3574 deg | -2.19% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 59.9856 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 17.2727 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 46.9583 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 10.8153 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 0 cy/mm | — | Zemax |
| 边缘有效光线 | — | 0 % | — | Zemax |
| 最大绝对畸变 | — | 1.6184 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 28.0091,
  "fnum": 3.9545,
  "r_sensor": 21.49,
  "surface_count": 11,
  "surface_types": [
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric"
  ],
  "materials": [
    "1.5337/56.23",
    "air",
    "1.6516/58.52",
    "1.4918/57.44",
    "air",
    "air",
    "1.6073/26.65",
    "1.6516/58.52",
    "air",
    "1.5168/64.17",
    "air"
  ]
}
```

### 最终结构

该结构已完成正式交付。

```json
{
  "foclen": 28.4701,
  "fnum": 3.9296,
  "r_sensor": 21.49,
  "surface_count": 11,
  "surface_types": [
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric"
  ],
  "materials": [
    "h-k51",
    "air",
    "h-lak7a",
    "h-k51",
    "air",
    "air",
    "h-zf1",
    "h-zpk1a",
    "air",
    "h-qk3l",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-154100\agents\optimization\views\turns.json`
