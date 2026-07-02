# 初始结构选择经验

- **透镜家族与视场匹配**：When 目标 FOV 在 40°–60° 且为标准焦段，prefer 选择 Double Gauss 类对称结构（如 native FOV 40° 种子用于 43° 目标），avoid 使用反远距或 Telephoto 以免引入不必要的畸变与场曲校正负担。
- **一阶量优先与 F 数宽容度**：When 评估种子，prefer 原生 EFL 和 FOV 最接近的种子；F 数偏差容忍度可放宽至 >2 档，avoid 因过度纠结初始 F 数而错失优秀对称拓扑。
- **大光圈种子适度降维**：When 目标 F 数中等（如 F/2.8–F/3.0），prefer 选择 F 数略小（如 F/1.8）的 Double Gauss 种子进行降维；avoid 盲目选择超大光圈（如 F/1.4）种子，以免初始结构过于复杂导致优化难以收敛。
- **光阑位置与像差平衡**：When 使用 Double Gauss 种子，prefer 光阑置于前中组之间以平衡球差与彗差；When 使用反远距种子，prefer 光阑置于后组前方以控制像方 CRA 和畸变。
- **非球面策略与后组侧重**：When 目标 F 数 ≤ F/3.0 或需严格控制总面数，prefer 在 Double Gauss 种子后组保留 1-2 个非球面，提供高阶自由度以突破球面局部极小并简化整体结构。
- **种子面数与复杂度控制**：When 目标面数明确，prefer 选择面数相近或略多（差异 ≤20%）的经典种子；avoid 初始面数过少，以免后期强行拆分胶合组导致结构失控。
- **薄型结构与后焦约束**：When 设计薄型镜头（如 BFL/TTL < 0.2）且 FOV 中等，prefer Double Gauss 或 Telephoto 结构；avoid 盲目使用反远距导致 TTL 超标。
- **缩放后一阶验证**：When 将种子缩放至特定 TTL，must 预先验证 BFL；unless 缩放后 BFL 留有充足机械余量，avoid 进入全优化。
- **DeepLens 兼容的初始结构**：When 准备自动化优化流水线，prefer 曲率和厚度分布平滑、无极端边缘厚度的种子；avoid 初始结构存在过度弯曲或极薄空气间隔。
