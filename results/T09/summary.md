# LensBot 结果摘要

- Generated at: 2026-09-22T23:12:24
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050`

## 设计要求

T09：设计一支可见光 RGB 长焦成像镜头，用于无限远目标。要求有效焦距为 135 mm，对角全视场为 18°，F 数为 5.6，对应约 42.8 mm 的像面直径。初始后焦距设为 30 mm，初始总厚度设为 150 mm。

| 参数 | 输入值 |
|---|---:|
| 焦距 | 135 mm |
| F 数 | 5.6 |
| 全视场 | 18 deg |
| 初始后焦距 BFL | 30 mm |
| 初始总长 TTL | 150 mm |

## 结论

Agent 判断：暂无法判断。Chosen candidate-002 (seed_159, 4-element all-spherical internal-stop Tessar) is the most contract-faithful and physically feasible of four optimized candidates: all protected first-order targets within ~2% (EFL 133.30 mm -1.26%, F/# 5.489 -1.98%, derived FOV 18.22 deg, imgh 21.38 mm -0.09%), BFL/TTL near starting geometry, min vertex spacing 9.10 mm, and the best MTF of the set. Status is 'uncertain' not 'pass': every exact target has no stated tolerance (all unknown_tolerance, pass_eligible false) so acceptance cannot be established, and edge-field polychromatic spot (~148 um) with edge MTF50 ~13-14 cy/mm is only moderate. Selection rule applied: the 6-element Double Gauss offered better EFL/distortion but at a 3.4x worse protected F/# (trade, not improvement), and the asphere probe failed outright (F/# -34%, edge distortion 114%, edge MTF50 ~0.5 cy/mm).

> 交付记录：有效产物已提交。仅表示优化智能体已提交并通过必需文件检查，不代表任何光学指标达标。

## 重要结果与证据

| 指标 | 目标 | 结果 | 相对偏差 | 来源 |
|---|---:|---:|---:|---|
| 有效焦距 | 135 mm | 133.666 mm | -0.99% | Zemax（另有 DeepLens） |
| 工作 F 数 | 5.6 | 5.4982 | -1.82% | Zemax（另有 DeepLens） |
| 全视场 | 18 deg | 18.0426 deg | +0.24% | Zemax（另有 DeepLens） |
| 总长 TTL（输入初值与最终实测） | — | 149.9542 mm | — | 最终结构（另有 输入初值） |
| 后焦距 BFL（输入初值与最终实测） | — | 31.7844 mm | — | 最终结构（另有 输入初值） |
| 最大 RMS 光斑 | — | 160.6302 um | — | Zemax（另有 DeepLens） |
| 中心 FFT MTF50 | — | 5.7828 cy/mm | — | Zemax |
| 边缘 FFT MTF50 | — | 1.7711 cy/mm | — | Zemax |
| 边缘有效光线 | — | 100 % | — | Zemax |
| 最大绝对畸变 | — | 1.4934 % | — | Zemax（另有 DeepLens） |

## 结构摘要

### 初始结构

```json
{
  "foclen": 134.9981,
  "fnum": 4.8704,
  "r_sensor": 21.38,
  "surface_count": 9,
  "surface_types": [
    "Spheric",
    "Aspheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture"
  ],
  "materials": [
    "1.5337/56.23",
    "air",
    "1.6516/58.52",
    "air",
    "1.4918/57.44",
    "air",
    "1.6073/26.65",
    "air",
    "air"
  ]
}
```

### 最终结构

该结构已完成正式交付。

```json
{
  "foclen": 133.305,
  "fnum": 5.4895,
  "r_sensor": 21.38,
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
    "h-k51",
    "h-f4",
    "air"
  ]
}
```

## 文件索引

- 最终结构 JSON：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\final\final.json`
- 最终结构 Zemax：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\final\final.zmx`
- 规范化证据：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\evidence.json`
- 标量指标：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\metrics.json`
- 光学设计总结：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\report.html`
- Zemax 验证：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\verification\zemax\zemax_report.json`
- 优化审计：`C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260922-214050\agents\optimization\views\turns.json`
