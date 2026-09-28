# LensBot 结果摘要

- Generated at: 2026-09-23T17:20:42
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828`

## 设计要求

T10：设计一支可见光 RGB 高速标准成像镜头，用于无限远目标。要求有效焦距为 50 mm，对角全视场为 47°，F 数为 2.0，对应约 43.5 mm 的像面直径。初始后焦距设为 18 mm，初始总厚度设为 75 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 50 mm |
| F 数 | 2 |
| 全视场 | 47 deg |
| 初始后焦距 BFL | 18 mm |
| 初始总长 TTL | 75 mm |

## 结论

Agent 判断：暂无法判断。Seed_198 (L_002 Double Gauss, internal stop, all-spherical) optimized to a physically feasible design with all three exact first-order targets within 0.5%: EFL 49.94 mm (-0.11%), FOV 47.05 deg (+0.10%), F/# 1.990 (-0.50%), packaging preserved (BFL 17.73 mm vs 18 starting, TTL 75.71 mm vs 75, no surface overlap, min spacing 2.95 mm). Image quality is moderate: polychromatic RMS spot 34.8/47.7/98.9 um center/mid/edge, distortion <=2.6%, geometric MTF50 ~5.9 cy/mm on axis and edge tangential/sagittal 12.2/6.0 cy/mm (persistent ~2x edge astigmatism); effective-ray fraction was not reported so edge conclusions are coverage-limited. The contract states exact targets with no tolerances, so acceptance is unknown_tolerance and a pass cannot be claimed; no explicit constraint is measurably violated.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 50 mm | 50.0197 mm | +0.04% | Zemax（另有 DeepLens） |
| 工作 F 数 | 2 | 1.9732 | -1.34% | Zemax（另有 DeepLens） |
| 全视场 | 47 deg | 46.577 deg | -0.90% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 75.7104 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 17.728 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 89.0867 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 7.5058 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 2.2963 cy/mm | — | Zemax |
| 边缘有效光线 | — | 99.5556 % | — | Zemax |
| 最大绝对畸变 | — | 1.5007 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 50.0027,
  "fnum": 1.9734,
  "r_sensor": 21.74,
  "surface_count": 13,
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
    "air",
    "1.6074/56.65",
    "air"
  ]
}
```

### 最终结构

该结构已完成正式交付。

```json
{
  "foclen": 49.9462,
  "fnum": 1.9902,
  "r_sensor": 21.74,
  "surface_count": 13,
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
    "h-zk9b",
    "air",
    "h-k9l",
    "air",
    "h-zk11",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-153828\agents\optimization\views\turns.json`
