# LensBot Generation Report

- Generated at: 2026-04-22T15:36:52
- Result directory: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260422-142710`

## User Input

```json
{
  "mode": "nl",
  "prompt": "设计一个 Cooke triplet 风格的相机镜头，焦距 35 mm，F/4，全视场角 40 度，后焦距 25 mm，总长 55 mm。",
  "params": {
    "exp_name": "Auto lens design",
    "seed": null,
    "foclen": 85.0,
    "fov": 40.0,
    "fnum": 4.0,
    "bfl": 18.0,
    "thickness": 120.0,
    "surf_list": [
      [
        "Spheric",
        "Spheric"
      ],
      [
        "Spheric",
        "Spheric"
      ],
      [
        "Spheric",
        "Spheric",
        "Spheric"
      ],
      [
        "Aperture"
      ],
      [
        "Spheric",
        "Spheric",
        "Spheric"
      ],
      [
        "Spheric",
        "Aspheric"
      ],
      [
        "Spheric",
        "Aspheric"
      ]
    ],
    "curriculum": {
      "lrs": [
        0.001,
        0.0001,
        0.01,
        0.0001
      ],
      "iterations": 3000,
      "test_per_iter": 100,
      "optim_mat": false,
      "match_mat": false,
      "shape_control": true,
      "num_ring": 16,
      "num_arm": 8,
      "spp": 512,
      "scale_pupil": 1.1,
      "aper_start_ratio": 0.25,
      "weight_dropout": 0.1,
      "w_focus": 0.1,
      "w_reg": 0.05
    },
    "fine_tune": {
      "lrs": [
        0.0001,
        1e-05,
        0.001,
        1e-05
      ],
      "iterations": 2000,
      "test_per_iter": 100,
      "centroid": false,
      "optim_mat": false,
      "shape_control": true,
      "num_ring": 32,
      "num_arm": 8,
      "spp": 512,
      "scale_pupil": 1.05,
      "weight_dropout": 0.0,
      "w_focus": 1.0,
      "w_reg": 0.1,
      "num_warmup_steps": 100
    }
  }
}
```

## Parsed Requirements

```json
{
  "exp_name": "Auto lens design",
  "seed": 64461,
  "foclen": 35.0,
  "fov": 40.0,
  "fnum": 4.0,
  "bfl": 25.0,
  "thickness": 55.0,
  "surf_list": [
    [
      "Spheric",
      "Spheric"
    ],
    [
      "Spheric",
      "Spheric"
    ],
    [
      "Aperture"
    ],
    [
      "Spheric",
      "Aspheric"
    ]
  ],
  "curriculum": {
    "lrs": [
      0.001,
      0.0001,
      0.01,
      0.0001
    ],
    "iterations": 3000,
    "test_per_iter": 100,
    "optim_mat": false,
    "match_mat": false,
    "shape_control": true,
    "num_ring": 16,
    "num_arm": 8,
    "spp": 512,
    "scale_pupil": 1.1,
    "aper_start_ratio": 0.25,
    "weight_dropout": 0.1,
    "w_focus": 0.1,
    "w_reg": 0.05
  },
  "fine_tune": {
    "lrs": [
      0.0001,
      1e-05,
      0.001,
      1e-05
    ],
    "iterations": 2000,
    "test_per_iter": 100,
    "centroid": false,
    "optim_mat": false,
    "shape_control": true,
    "num_ring": 32,
    "num_arm": 8,
    "spp": 512,
    "scale_pupil": 1.05,
    "weight_dropout": 0.0,
    "w_focus": 1.0,
    "w_reg": 0.1,
    "num_warmup_steps": 100
  }
}
```

## Optimized Result

- Summary: Lens design finished. spot_rms_edge=92.593um, distortion_edge=-0.6907429080456495%, MTF50_center_tan=24.18264572189705 cy/mm.
- Starting point: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260422-142710\starting-point.json`
- Curriculum lens: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260422-142710\curriculum.json`
- Final lens JSON: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260422-142710\final.json`
- Final lens ZMX: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260422-142710\final.zmx`
- Metrics file: `C:\Users\Miggua\Desktop\Workspace\LensBot\results\20260422-142710\metrics.json`

## Key Metrics

```json
{
  "rfov": "0.3422531485557556",
  "fnum": 4.037124534324032,
  "r_sensor": 12.74,
  "spot_rms_um_center": 31.4062,
  "spot_rms_um_edge": 92.593,
  "distortion_pct_edge": -0.6907429080456495,
  "mtf50_center_tan_cy_mm": 24.18264572189705,
  "mtf50_edge_tan_cy_mm": 11.820740396375646,
  "zemax_ok": true,
  "zemax_efl_mm": 35.53444280275914,
  "zemax_fnum": 4.0371,
  "zemax_fov_deg": 38.61308070888803,
  "zemax_distortion_pct_edge": 1.3387270220149183,
  "zemax_spot_rms_edge_um": 108.85892413850657,
  "zemax_mtf50_center_tan_cy_mm": 8.234420200473126,
  "zemax_mtf50_edge_tan_cy_mm": 3.754743939969343
}
```

## Starting Structure Summary

```json
{
  "foclen": 369.0109,
  "fnum": 41.2772,
  "r_sensor": 12.74,
  "surface_count": 7,
  "surface_types": [
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture",
    "Spheric",
    "Aspheric"
  ],
  "materials": [
    "n-sf11",
    "air",
    "n-sk16",
    "air",
    "air",
    "h-k9l",
    "air"
  ]
}
```

## Final Structure Summary

```json
{
  "foclen": 35.9764,
  "fnum": 4.0371,
  "r_sensor": 12.74,
  "surface_count": 7,
  "surface_types": [
    "Spheric",
    "Spheric",
    "Spheric",
    "Spheric",
    "Aperture",
    "Spheric",
    "Aspheric"
  ],
  "materials": [
    "h-zf13",
    "air",
    "h-zk9b",
    "air",
    "air",
    "h-k9l",
    "air"
  ]
}
```

## Optimized Lens JSON

```json
{
  "info": "None",
  "foclen": 35.9764,
  "fnum": 4.0371,
  "r_sensor": 12.74,
  "(d_sensor)": 54.3934,
  "(sensor_size)": [
    18.0171,
    18.0171
  ],
  "surfaces": [
    {
      "idx": 0,
      "type": "Spheric",
      "r": 12.1015,
      "(c)": 0.0273,
      "roc": 36.5914,
      "(d)": 0.0,
      "mat2": "h-zf13",
      "d_next": 6.1776
    },
    {
      "idx": 1,
      "type": "Spheric",
      "r": 10.444,
      "(c)": 0.0039,
      "roc": 258.3142,
      "(d)": 6.1776,
      "mat2": "air",
      "d_next": 6.0253
    },
    {
      "idx": 2,
      "type": "Spheric",
      "r": 6.5893,
      "(c)": -0.0182,
      "roc": -54.8275,
      "(d)": 12.2029,
      "mat2": "h-zk9b",
      "d_next": 2.89
    },
    {
      "idx": 3,
      "type": "Spheric",
      "r": 5.5225,
      "(c)": 0.0052,
      "roc": 193.6983,
      "(d)": 15.0929,
      "mat2": "air",
      "d_next": 4.3666
    },
    {
      "idx": 4,
      "type": "Aperture",
      "r": 3.4325,
      "(d)": 19.4595,
      "mat2": "air",
      "is_square": false,
      "d_next": 4.5116
    },
    {
      "idx": 5,
      "type": "Spheric",
      "r": 5.935,
      "(c)": 0.0175,
      "roc": 57.2999,
      "(d)": 23.9711,
      "mat2": "h-k9l",
      "d_next": 6.082
    },
    {
      "idx": 6,
      "type": "Aspheric",
      "r": 7.2244,
      "(c)": -0.0405,
      "roc": -24.6941,
      "d": 30.0531,
      "k": -2.2375,
      "ai": [
        2.708653e-06,
        1.688416e-08,
        -2.669991e-10,
        -7.420105e-12,
        -8.844114e-14,
        -1.631146e-16,
        2.003575e-17,
        6.460961e-19
      ],
      "use_ai2": false,
      "mat2": "air",
      "(ai4)": 2.708653e-06,
      "(ai6)": 1.688416e-08,
      "(ai8)": -2.669991e-10,
      "(ai10)": -7.420105e-12,
      "(ai12)": -8.844114e-14,
      "(ai14)": -1.631146e-16,
      "(ai16)": 2.003575e-17,
      "(ai18)": 6.460961e-19,
      "d_next": 24.3402
    }
  ]
}
```
