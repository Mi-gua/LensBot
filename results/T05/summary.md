# LensBot 结果摘要

- Generated at: 2026-09-22T15:16:37
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839`

## 设计要求

T05：设计一支可见光 RGB 大光圈标准成像镜头，用于无限远目标。要求有效焦距为 50 mm，对角全视场为 47°，F 数为 2.8，对应约 43.5 mm 的像面直径。初始后焦距设为 18 mm，初始总厚度设为 75 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 50 mm |
| F 数 | 2.8 |
| 全视场 | 47 deg |
| 初始后焦距 BFL | 18 mm |
| 初始总长 TTL | 75 mm |

## 结论

Agent 判断：暂无法判断。Selected candidate-003, best of the seed_198 all-spherical 6-element Double Gauss line: physically feasible (min vertex spacing 2.65 mm, 0 aspheres, all distortion rays valid) and close to contract but not exact - ray-traced EFL 51.26 mm (+2.5%), sensor-implied FOV 45.97 deg (-2.2%), working F/2.833 (+1.2%). Since the contract states these as exact with no tolerance, compliance cannot be certified (all three marked unknown_tolerance). Image quality is only modest (RMS spot 44/55/72 um center/mid/edge, center geometric MTF50 7.4 cy/mm, edge distortion -4.2%), and edge-ray validity fractions are not reported, so edge performance stays unconfirmed. Reported as a weak-but-fully-evidenced outcome, not a validated pass nor a demonstrated constraint violation.

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 50 mm | 51.3126 mm | +2.63% | Zemax（另有 DeepLens） |
| 工作 F 数 | 2.8 | 2.807 | +0.25% | Zemax（另有 DeepLens） |
| 全视场 | 47 deg | 45.5111 deg | -3.17% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 75.24 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 16.739 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 71.9216 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 6.1424 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 4.2526 cy/mm | — | Zemax |
| 边缘有效光线 | — | 100 % | — | Zemax |
| 最大绝对畸变 | — | 2.8785 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 50.0027,
  "fnum": 2.7309,
  "r_sensor": 21.74,
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
    "Spheric"
  ],
  "materials": [
    "1.5337/56.23",
    "air",
    "1.6516/58.52",
    "air",
    "1.4918/57.44",
    "air",
    "air",
    "1.6073/26.65",
    "air",
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
  "foclen": 51.2567,
  "fnum": 2.8331,
  "r_sensor": 21.74,
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
    "Spheric"
  ],
  "materials": [
    "h-k51",
    "air",
    "h-zpk1a",
    "air",
    "h-k51",
    "air",
    "air",
    "h-f4",
    "air",
    "h-zk9b",
    "air",
    "h-k9l",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-134839\agents\optimization\views\turns.json`
