# LensBot 结果摘要

- Generated at: 2026-09-22T18:53:37
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547`

## 设计要求

T07：设计一支可见光 RGB 大像场成像镜头，用于无限远目标。要求有效焦距为 35 mm，对角全视场为 63°，F 数为 3.5，对应约 42.9 mm 的像面直径。初始后焦距设为 18 mm，初始总厚度设为 65 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 35 mm |
| F 数 | 3.5 |
| 全视场 | 63 deg |
| 初始后焦距 BFL | 18 mm |
| 初始总长 TTL | 65 mm |

## 结论

Agent 判断：暂无法判断。Selected candidate-004 (seed_198: 5-group Double Gauss, internal stop, one asphere on the last surface) as the best-evidenced prescription. Matched analysis: EFL 36.02 mm (+2.9% vs exact 35), F/3.655 (+4.4% vs 3.5), FOV 61.55 deg (-2.3%), imgh 21.45 mm exact; geometry physically valid (min vertex spacing 1.17 mm, TTL 64.64, BFL 17.75). Field-resolved image quality is the strongest of the shortlist: polychromatic RMS spot 26.8 / 30.7 / 31.5 um (center/mid/edge, max 39.3) and geometric MTF50 8.8 cyc/mm center, 14.4 / 7.9 cyc/mm edge tan/sag, with internally consistent distortion (-2.1% at edge). No user tolerance is stated for any exact target, so first-order compliance is unknown_tolerance and neither pass nor fail can be asserted; image quality is moderate but has no stated acceptance threshold. Hence uncertain, not pass.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 35 mm | 36.3194 mm | +3.77% | Zemax（另有 DeepLens） |
| 工作 F 数 | 3.5 | 3.6875 | +5.36% | Zemax（另有 DeepLens） |
| 全视场 | 63 deg | 60.944 deg | -3.26% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 64.6425 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 17.7472 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 45.3555 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 9.743 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 8.8363 cy/mm | — | Zemax |
| 边缘有效光线 | — | 63.2222 % | — | Zemax |
| 最大绝对畸变 | — | 1.2423 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 35.0064,
  "fnum": 3.4536,
  "r_sensor": 21.45,
  "surface_count": 13,
  "surface_types": [
    "Spheric",
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
    "Aspheric"
  ],
  "materials": [
    "1.5337/56.23",
    "1.6516/58.52",
    "air",
    "1.4918/57.44",
    "1.6073/26.65",
    "air",
    "air",
    "1.6516/58.52",
    "1.5168/64.17",
    "air",
    "1.6074/56.65",
    "1.6200/36.43",
    "air"
  ]
}
```

### 最终结构

该结构已完成正式交付。

```json
{
  "foclen": 36.0148,
  "fnum": 3.6547,
  "r_sensor": 21.45,
  "surface_count": 13,
  "surface_types": [
    "Spheric",
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
    "Aspheric"
  ],
  "materials": [
    "h-bak7",
    "h-zk21",
    "air",
    "h-k51",
    "h-f4",
    "air",
    "air",
    "h-zpk5",
    "h-k9l",
    "air",
    "h-zpk1a",
    "h-tf3l",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-164547\agents\optimization\views\turns.json`
