# LensBot 结果摘要

- Generated at: 2026-09-23T20:10:08
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906`

## 设计要求

T12：设计一支可见光 RGB 高速中焦成像镜头，用于无限远目标。要求有效焦距为 85 mm，对角全视场为 29°，F 数为 2.0，对应约 44.0 mm 的像面直径。初始后焦距设为 25 mm，初始总厚度设为 105 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 85 mm |
| F 数 | 2 |
| 全视场 | 29 deg |
| 初始后焦距 BFL | 25 mm |
| 初始总长 TTL | 105 mm |

## 结论

Agent 判断：暂无法判断。Chosen artifact candidate-004 (all-spherical internal-stop Double Gauss lineage from seed_198; best of candidate-001..004, all verified passes). Measured first-order: EFL 84.51 mm (-0.58% vs 85), FOV 29.16 deg (+0.55%), F/# 1.982 (-0.90% vs 2.0); TTL 106.4 mm / BFL 26.0 mm vs starting 105/25; min vertex spacing 5.59 mm (physically feasible, no self-intersection). Image quality is only moderate: polychromatic RMS spot 63/97/157 um center/mid/edge, geometric single-wavelength MTF50 3.98 cy/mm center and 9.39/7.71 cy/mm edge tan/sag, distortion <=1.67%. All three exact targets carry no user tolerance and spot/MTF have no acceptance threshold, with edge valid-ray fraction unreported; so compliance is unknown_tolerance (pass_eligible=false) rather than pass or fail. The DG line needed an LR reduction to stop trading the protected F/# for spot; after that it converged with all three first-order targets within ~0.9%.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 85 mm | 84.5908 mm | -0.48% | Zemax（另有 DeepLens） |
| 工作 F 数 | 2 | 1.9504 | -2.48% | Zemax（另有 DeepLens） |
| 全视场 | 29 deg | 28.8696 deg | -0.45% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 106.402 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 26.0124 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 165.3233 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 5.0345 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 1.7237 cy/mm | — | Zemax |
| 边缘有效光线 | — | 91.7778 % | — | Zemax |
| 最大绝对畸变 | — | 0.793 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 84.9969,
  "fnum": 1.956,
  "r_sensor": 21.98,
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
  "foclen": 84.5063,
  "fnum": 1.982,
  "r_sensor": 21.98,
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
    "h-k9l",
    "air",
    "h-zpk1a",
    "h-k51",
    "air",
    "air",
    "h-f4",
    "h-zk21",
    "air",
    "h-k51",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-182906\agents\optimization\views\turns.json`
