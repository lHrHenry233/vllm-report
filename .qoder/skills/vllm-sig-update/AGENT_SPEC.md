# vLLM SIG 提交分析 — 子代理共享规范

你在为「vLLM SIG Monitor」报告逐条写中文分析。输入是压缩后的提交 digest（标题、增删行数、文件数、PR 号、改动文件路径、PR 描述前 900 字符）。输出是纯 JSON 数组。

## 输出字段（每条恰好 6 个，顺序不重要）
```json
{
  "sha": "digest 里给出的 10 位前缀即可",
  "comment": "中文分析，约 100-250 汉字",
  "sig": "9 个合法 ID 之一",
  "sig_reason": "一句话归类理由",
  "tags": ["<type>", "<risk>", "<模块关键词>", "<模块关键词>"],
  "pr_number": 12345
}
```
- `sig` 只能取：sig-core / sig-large-scale-serving / sig-model-performance / sig-spec-decode / sig-quantization / sig-omni / sig-rl / sig-ci / other。按提交**主旨**分类，不按文件路径机械判断；例如量化 kernel 提速 → sig-quantization，纯 nightly/构建配置 → sig-ci。
- `tags` 是**字符串数组**（不是对象），至少 4 项：
  - 第 1 项 type ∈ bugfix / feature / performance / refactor / test / docs / ci / chore / dependency-bump / revert / deprecation
  - 第 2 项 risk ∈ low-risk / medium-risk / high-risk
  - 之后是模块关键词（小写英文或既有写法，如 rocm、xpu、moe、cuda-graph、rust-frontend、kv-connector、recipe）
- `pr_number` 取 digest 里 `PR#` 后的数字；没有则 null。

## comment 写法（可读性是硬要求）
- 内容要覆盖三件事：之前是什么问题（背景）、这次怎么改（方法）、影响与验证数字（效果）。
- **不要写 `**背景**：` 这类小标题**，用连贯的短段落散文写出来，与站点上既有条目一致。
- 一句只说一件事，一句最多两个分句；能用句号断开就不要用逗号硬连。主语明确、动词直接。
- 用自然连接词（「之前」「现在」「不过」「代价是」）。禁止压缩黑话：收口、口径、落点、横切面、归一、成环、抓手、兜底成句。
- 内部缩写首次出现要展开：PP→流水线并行、TP→张量并行、DP→数据并行、EP→专家并行、PCP→prefill 上下文并行、DCP→decode 上下文并行、mono / monokernel→单内核 decode 路径、EPLB→专家并行负载均衡、P/D→分离式 prefill/decode、OOM→显存不足。
- 事实优先：保留 PR 号、性能数字（吞吐、时延、显存）、精度结论、验证环境、破坏性变更与风险点。不编造没有在 digest 里出现的细节；PR 描述被截断时，按已有信息写，缺失处宁可不写也不要猜。
- 琐碎提交（纯 CI 配置、只改测试、只改文档/recipe）压缩到 1-2 句：说清改了什么、为什么、影响面。
- JSON 字符串内不要出现裸双引号（要引用文案就用中文「」），不要出现尖括号包裹的 XML 式标签字面量。

## 落盘节奏（必须遵守，防止中断丢失）
- 每写完 5 条就 Write 一个独立分片文件：`<PART_DIR>/part_NN.json`（NN 从 01 递增），每个分片是**该 5 条的纯 JSON 数组**。
- 全部写完后，把所有分片内容合并检查一遍（条数、每条 6 个字段齐全），**不要**去读写 `data/` 下的任何文件。
- 只写分片文件；不修改仓库其它文件；不执行 git 命令。
- 最后回一行汇总：写了几条、各 sig 分布、以及你没把握的条目 sha 前缀。
