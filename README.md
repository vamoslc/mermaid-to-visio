# Mermaid → Visio

把 **任意 Mermaid 图**（流程图、类图、ER、时序、状态、饼图等）转换成 Microsoft Visio `.vsdx`。

提供：

- 命令行工具 `mermaid_to_visio.py`
- 图形界面（主题配色 + 实时预览 + 单文件/批量导出）
- 一键打包为 Windows 可执行文件 `MermaidToVisio.exe`

## 功能

| 能力 | 说明 |
|------|------|
| 全图类型 | flowchart / sequence / class / ER / state / gantt / pie / mindmap 等 |
| 颜色风格 | 彩色 Redux、经典蓝、森林绿、中性灰、深色 |
| 导出模式 | `auto` / `connected`（可编辑连接） / `geometry`（SVG 几何） / `picture`（整图嵌入） |
| 预览 | GUI 内实时 PNG 预览，换主题即时刷新 |
| 批量 | 选文件夹或多文件，批量输出 `.vsdx`，保留相对目录结构 |

### 导出策略（auto）

1. **connected**：flowchart / sequence / state / class → 可编辑形状 + 粘合连接线  
2. **geometry**：其余类型 → Mermaid SVG 几何导入 Visio 形状  
3. **picture**：兜底 → 高清 PNG 整页嵌入

## 环境要求

- Windows 10/11（GUI / exe）
- Python 3.10+（开发与命令行）
- 依赖见 `requirements.txt`（核心为 [`mermaid-render`](https://pypi.org/project/mermaid-render/)）

## 安装

```bash
cd tools/mermaid_to_visio
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 图形界面

```bash
python gui_app.py
# 或
启动GUI.bat
```

已打包的程序：

```text
dist/MermaidToVisio.exe
```

界面操作要点：

1. 粘贴或打开 `.mmd` / `.mermaid` / `.md`（Markdown 会提取 \`\`\`mermaid 代码块）
2. 选择颜色风格色块 → 右侧预览
3. 「导出 Visio…」单文件导出；「批量转 Visio…」选目录/多文件批量导出（`Ctrl+B`）

## 命令行

```bash
# 单文件
python mermaid_to_visio.py examples/flowchart.mmd -o out/flowchart.vsdx

# 指定主题与模式
python mermaid_to_visio.py examples/er.mmd -o out/er.vsdx --theme forest --mode auto

# 批量（递归扫描 .mmd / .mermaid / .md）
python mermaid_to_visio.py --batch ./examples -o ./out/batch

# 从 stdin
type diagram.mmd | python mermaid_to_visio.py - -o out.vsdx
```

常用参数：

| 参数 | 说明 |
|------|------|
| `-o` | 输出路径；批量时为输出目录 |
| `--theme` | `redux-color` / `default` / `forest` / `neutral` / `dark` |
| `--mode` | `auto` / `connected` / `geometry` / `picture` |
| `--connectors` | `right-angle` / `straight` / `mermaid`（connected 模式） |
| `--batch` | 批量转换目录 |

## 打包 exe

```bash
build_exe.bat
# 或
python -m PyInstaller --noconfirm build_exe.spec
```

产物：`dist/MermaidToVisio.exe`（约 26MB，免安装运行）。

## 目录结构

```text
mermaid_to_visio/
├── mermaid_to_visio.py   # 转换核心 + CLI
├── gui_app.py            # 图形界面
├── build_exe.spec        # PyInstaller 配置
├── build_exe.bat         # 一键打包
├── 启动GUI.bat
├── requirements.txt
├── examples/             # 示例 .mmd
└── dist/MermaidToVisio.exe
```

## 示例

`examples/` 下包含 flowchart、class、ER、sequence、state、pie 示例，可直接试转：

```bash
python mermaid_to_visio.py --batch ./examples -o ./out
```

## 说明与限制

- **connected** 目前语义级支持：flowchart、sequence、state、class；其它类型走 geometry/picture。
- 中文等非 Noto Sans 覆盖字符，预览/导出可能依赖系统字体回退。
- geometry 模式为形状几何导入，**无语义粘合连接**；需要“看着像 Mermaid”时优先用该模式或 picture。
- 本工具不依赖本机安装 Microsoft Visio 即可生成 `.vsdx`；编辑建议用 Visio 或兼容软件打开验证。

## License

MIT（转换引擎 `mermaid-render` 及其依赖遵循各自上游许可证）
