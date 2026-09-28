# LensBot 结果摘要

- Generated at: 2026-09-28T16:55:21
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644`

## 设计要求

T03：设计一支可见光 RGB 标准成像镜头，用于无限远目标。要求有效焦距为 50 mm，对角全视场为 47°，F 数为 4.0，对应约 43.5 mm 的像面直径。初始后焦距设为 18 mm，初始总厚度设为 75 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 50 mm |
| F 数 | 4 |
| 全视场 | 47 deg |
| 初始后焦距 BFL | 18 mm |
| 初始总长 TTL | 75 mm |

## 结论

Agent 判断：暂无法判断。Selected candidate-004 (reduced internal-stop Double Gauss, 11 surfaces / 6 elements / 0 aspheric, lineage seed_198) after a 2000-iteration curriculum plus four 2500-step refinement blocks. All three exact targets remain low-single-digit off: EFL 49.49 mm (-1.02%), derived FOV 47.43 deg (+0.92%), F-number 3.924 (-1.90%), i.e. every deviation <=1.9%. The contract states exact targets with no acceptance tolerance, so each is unknown_tolerance and pass_eligible is false; no validated pass/fail can be claimed. Imaging is moderate but internally consistent (polychromatic RMS spot ~20.0/26.0/35.7 um center/mid/edge; single-wavelength geometric MTF50 ~11.7 cy/mm center, ~11.8-19.3 edge), yet the edge-spot valid-ray fraction is null, so edge image quality stays unconfirmed. Packaging holds (BFL 16.88 mm vs 18 initial, TTL 75.01 mm, min vertex spacing 3.14 mm). Main caveat/tradeoff: candidate-002 is tighter on the headline EFL (-0.37%) but carries a larger F-number residual (-2.51%) and worse imaging, so no candidate dominates.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 50 mm | 49.6929 mm | -0.61% | Zemax（另有 DeepLens） |
| 工作 F 数 | 4 | 3.9406 | -1.49% | Zemax（另有 DeepLens） |
| 全视场 | 47 deg | 46.9621 deg | -0.08% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 75.0075 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 16.8809 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 41.2113 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 14.4077 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 5.4633 cy/mm | — | Zemax |
| 边缘有效光线 | — | 100 % | — | Zemax |
| 最大绝对畸变 | — | 0.9953 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 50.0027,
  "fnum": 3.9377,
  "r_sensor": 21.74,
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
  "foclen": 49.4864,
  "fnum": 3.9237,
  "r_sensor": 21.74,
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
    "h-zk11",
    "air",
    "h-k51",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260928-152644\agents\optimization\views\turns.json`
