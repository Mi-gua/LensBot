# LensBot 结果摘要

- Generated at: 2026-09-22T12:58:44
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043`

## 设计要求

T04：设计一支可见光 RGB 中焦成像镜头，用于无限远目标。要求有效焦距为 85 mm，对角全视场为 29°，F 数为 4.0，对应约 44.0 mm 的像面直径。初始后焦距设为 25 mm，初始总厚度设为 105 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 85 mm |
| F 数 | 4 |
| 全视场 | 29 deg |
| 初始后焦距 BFL | 25 mm |
| 初始总长 TTL | 105 mm |

## 结论

Agent 判断：暂无法判断。Optimized Double Gauss (candidate-002) is the best-balanced candidate: it meets all three exact first-order targets within fractional error (EFL 84.82 mm = -0.22%, FOV 29.06 deg = +0.20%, F/# 4.023 = +0.59%) with physically feasible geometry (min vertex spacing 5.77 mm, distortion valid-fraction 1.0) and it roughly halves the edge RMS spot versus the Elmar seed (159 -> 98 um) while raising center MTF50 (4.69 -> 5.96 cy/mm). Acceptance cannot be certified, however: the contract states no tolerance and no spot/MTF requirement, and the delivered absolute image quality is soft (center/edge RMS spot 51/98 um; geometric single-wavelength MTF50 only ~6 cy/mm, which is a non-diffraction analysis). The three exact targets are therefore measured as unknown_tolerance, and no independent (e.g. Zemax) cross-check was performed, so the optical verdict is uncertain rather than pass.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 85 mm | 85.1143 mm | +0.13% | Zemax（另有 DeepLens） |
| 工作 F 数 | 4 | 4.0247 | +0.62% | Zemax（另有 DeepLens） |
| 全视场 | 29 deg | 28.7686 deg | -0.80% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 105.3012 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 25.2316 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 120.3019 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 6.418 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 3.866 cy/mm | — | Zemax |
| 边缘有效光线 | — | 100 % | — | Zemax |
| 最大绝对畸变 | — | 0.3654 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 84.9969,
  "fnum": 3.8537,
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
    "1.6073/26.65",
    "air",
    "1.6074/56.65",
    "1.4918/57.44",
    "air",
    "air",
    "1.7847/25.68",
    "1.7847/25.68",
    "air",
    "1.6200/36.37",
    "air"
  ]
}
```

### 最终结构

该结构已完成正式交付。

```json
{
  "foclen": 84.8162,
  "fnum": 4.0235,
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
    "h-f4",
    "air",
    "h-zpk5",
    "h-k51",
    "air",
    "air",
    "h-zf13",
    "h-zf13",
    "air",
    "h-f4",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-110043\agents\optimization\views\turns.json`
