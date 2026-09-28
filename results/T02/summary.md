# LensBot 结果摘要

- Generated at: 2026-09-28T15:03:36
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853`

## 设计要求

T2：设计一支可见光 RGB 成像镜头，用于无限远目标。要求有效焦距为 35 mm，对角全视场为 44°，F 数为 4.0，对应约 28.3 mm 的像面直径。初始后焦距设为 12 mm，初始总厚度设为 50 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 35 mm |
| F 数 | 4 |
| 全视场 | 44 deg |
| 初始后焦距 BFL | 12 mm |
| 初始总长 TTL | 50 mm |

## 结论

Agent 判断：暂无法判断。Chosen prescription is candidate-004 (Double Gauss, seed_198, reduced-LR refinement): the most balanced and best-imaging candidate. First-order residuals are all a few percent but non-zero (EFL 35.852 mm = +2.43%; F/# 3.922 = -1.95%; derived FOV 43.05 deg = -2.16% with imgh pinned at 14.14), and the contract states foclen/fov/fnum as 'exact' with no tolerance, so exact-target compliance is unknown_tolerance and cannot be called pass or fail. Image quality is the best of the compared candidates but only geometric, single-wavelength, with unreported spot valid-fraction: center/edge RMS spot 20.0/40.5 um, edge distortion -4.54%, center MTF50 ~10.5 cy/mm. Packaging is satisfied (TTL 50.2 mm, BFL 11.6 mm, min vertex spacing 2.08 mm), all-spherical, 11 surfaces.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 35 mm | 36.0357 mm | +2.96% | Zemax（另有 DeepLens） |
| 工作 F 数 | 4 | 3.9392 | -1.52% | Zemax（另有 DeepLens） |
| 全视场 | 44 deg | 42.6224 deg | -3.13% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 50.2022 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 11.5976 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 50.7055 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 12.4743 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 19.2495 cy/mm | — | Zemax |
| 边缘有效光线 | — | 100 % | — | Zemax |
| 最大绝对畸变 | — | 2.2723 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 35.0006,
  "fnum": 3.9584,
  "r_sensor": 14.14,
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
  "foclen": 35.8508,
  "fnum": 3.9221,
  "r_sensor": 14.14,
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
    "h-tf3l",
    "air",
    "air",
    "h-f4",
    "h-zk11",
    "air",
    "h-k51",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-102853\agents\optimization\views\turns.json`
