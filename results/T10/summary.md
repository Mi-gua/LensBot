# LensBot 结果摘要

- Generated at: 2026-09-23T14:55:45
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317`

## 设计要求

T10：设计一支可见光 RGB 大光圈广角成像镜头，用于无限远目标。要求有效焦距为 28 mm，对角全视场为 75°，F 数为 2.8，对应约 43.0 mm 的像面直径。初始后焦距设为 18 mm，初始总厚度设为 65 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 28 mm |
| F 数 | 2.8 |
| 全视场 | 75 deg |
| 初始后焦距 BFL | 18 mm |
| 初始总长 TTL | 65 mm |

## 结论

Agent 判断：暂无法判断。Selected candidate-002 (seed_198 Double Gauss + 1 asphere; 11 surfaces, 1 asphere): all three exact targets within ~2.5% — EFL 28.70 mm (+2.5% vs 28), full field 73.65 deg (-1.8% vs 75; derived as 2*atan(21.49/EFL) at the fixed 21.49 mm image height), working F/# 2.821 (+0.75% vs 2.8) — with physically feasible geometry (min vertex spacing 2.70 mm, BFL 18.27 mm, TTL 65.52 mm, all distortion rays valid) and usable field quality (RMS spot 48/67/174 um center/mid/edge, geometric MTF50 4.65 cy/mm center, edge distortion -3.3%). Verdict is uncertain, not pass: the contract states three exact targets with no stated tolerance (all status unknown_tolerance, pass_eligible=false), so acceptance cannot be certified. Chosen over candidate-003 because its better EFL/IQ came at the cost of protected F/# fidelity (+0.75% -> +2.1%) — a Pareto trade, not a dominating improvement. seed_104 (all-spherical inverted telephoto) was dominated on every metric and dropped.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 28 mm | 29.0643 mm | +3.80% | Zemax（另有 DeepLens） |
| 工作 F 数 | 2.8 | 2.8441 | +1.58% | Zemax（另有 DeepLens） |
| 全视场 | 75 deg | 72.7064 deg | -3.06% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 65.5247 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 18.2694 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 179.1677 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 5.2175 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 4.2372 cy/mm | — | Zemax |
| 边缘有效光线 | — | 100 % | — | Zemax |
| 最大绝对畸变 | — | 3.8247 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 28.0091,
  "fnum": 2.7644,
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
    "Aspheric"
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
  "foclen": 28.8125,
  "fnum": 2.8318,
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
    "Aspheric"
  ],
  "materials": [
    "h-k51",
    "air",
    "h-zk11",
    "h-k51",
    "air",
    "air",
    "h-f4",
    "h-zk9b",
    "air",
    "h-k9l",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260923-124317\agents\optimization\views\turns.json`
