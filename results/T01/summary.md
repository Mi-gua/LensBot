# LensBot 结果摘要

- Generated at: 2026-09-27T21:58:36
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025`

## 设计要求

T01：设计一支可见光 RGB 成像镜头，用于无限远目标。要求有效焦距为 25 mm，对角全视场为 40°，F 数为 4.0，对应约 18.2 mm 的像面直径。初始后焦距设为 8 mm，初始总厚度设为 35 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 25 mm |
| F 数 | 4 |
| 全视场 | 40 deg |
| 初始后焦距 BFL | 8 mm |
| 初始总长 TTL | 35 mm |

## 结论

Agent 判断：暂无法判断。Selected the Tessar split-triplet candidate-003 (curriculum 2000 + 3x2500 fine-tune steps; all-spherical, internal stop, 8 surfaces). It is the best of three independent families compared under one protocol (Tessar > internal-stop Double Gauss ~ Cooke triplet). All three exact contract targets remain off target: EFL 23.63 mm (-5.5%), F/# 3.839 (-4.0%), FOV 42.12 deg (+5.3%, derived from fixed image height); with no user tolerance these are unknown_tolerance, so no pass and no stated-constraint violation. Packaging is satisfied (TTL 33.03 mm, BFL 4.94 mm from an 8 mm start, min vertex spacing 1.61 mm). Image quality is moderate, not diffraction-limited: edge RMS spot ~39 um, geometric MTF50 up to ~33 cy/mm edge tangential (definition-scoped), edge distortion -3.4%.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 25 mm | 23.7297 mm | -5.08% | Zemax（另有 DeepLens） |
| 工作 F 数 | 4 | 3.8554 | -3.62% | Zemax（另有 DeepLens） |
| 全视场 | 40 deg | 41.7078 deg | +4.27% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 33.0272 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 4.9443 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 38.7976 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 17.0347 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 7.0145 cy/mm | — | Zemax |
| 边缘有效光线 | — | 84.4444 % | — | Zemax |
| 最大绝对畸变 | — | 1.3486 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 25.004,
  "fnum": 3.9575,
  "r_sensor": 9.1,
  "surface_count": 7,
  "surface_types": [
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture",
    "Spheric",
    "Spheric"
  ],
  "materials": [
    "1.5337/56.23",
    "air",
    "1.6516/58.52",
    "air",
    "air",
    "1.4918/57.44",
    "air"
  ]
}
```

### 最终结构

该结构已完成正式交付。

```json
{
  "foclen": 23.6287,
  "fnum": 3.8384,
  "r_sensor": 9.1,
  "surface_count": 8,
  "surface_types": [
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture",
    "Spheric",
    "Spheric",
    "Spheric"
  ],
  "materials": [
    "h-k9l",
    "air",
    "h-zk11",
    "air",
    "air",
    "h-k9l",
    "h-f4",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260927-180025\agents\optimization\views\turns.json`
