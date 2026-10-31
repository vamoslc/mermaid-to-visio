---
name: mermaid-to-visio
description: >-
  将 Mermaid 图（flowchart/类图/ER/时序/状态/饼图等）转为 Microsoft Visio .vsdx。
  在用户提到 Mermaid 转 Visio、.mmd/.mermaid 导出 .vsdx、批量转 Visio、选配色主题预览导出时使用。
  触发词：/mermaid-to-visio、mermaid→visio、转 vsdx。
---

# Mermaid → Visio

把任意 Mermaid 图转成可打开的 Visio `.vsdx`。本仓库自带 CLI、GUI 与批量能力。

## 何时使用

- 用户要「Mermaid 转 Visio / vsdx」
- 已有 `.mmd` / `.mermaid` / 含 \`\`\`mermaid 的 `.md`，需导出 Visio
- 需要批量转换，或指定颜色风格（彩色/经典蓝/森林绿/中性灰/深色）

## 工具位置（相对本仓库根）

| 文件 | 用途 |
|------|------|
| `mermaid_to_visio.py` | 转换核心 + CLI |
| `gui_app.py` | 图形界面（预览 + 主题 + 批量） |
| `examples/*.mmd` | 示例图 |
| `dist/MermaidToVisio.exe` | 已打包 GUI（若存在） |
| `requirements.txt` | Python 依赖 |

工作目录应设为**本仓库根目录**（含 `mermaid_to_visio.py` 的目录）。

## 依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

核心依赖：`mermaid-render>=0.14.1`、`Pillow`（GUI 预览）。

## 转换策略（必须遵守）

按 `auto` 模式级联，不要自己手写 VSDX XML：

1. **connected**：flowchart / sequence / state / class → 可编辑形状 + 粘合连接线  
2. **geometry**：ER / pie / gantt 等其余类型 → SVG 几何导入 Visio 形状  
3. **picture**：失败时兜底 → PNG 整页嵌入  

主题（`--theme`）：`redux-color`（默认）| `default` | `forest` | `neutral` | `dark`  
连接线（仅 connected）：`right-angle` | `straight` | `mermaid`  
模式（`--mode`）：`auto` | `connected` | `geometry` | `picture`

## 操作流程

### 1) 单文件转换

1. 确认输入是 Mermaid 源码或 `.mmd` / `.mermaid` / `.md`  
2. 若用户指定风格，映射到 `--theme`；未指定用 `redux-color`  
3. 执行：

```bash
python mermaid_to_visio.py <input.mmd> -o <output.vsdx> --theme <theme> --mode auto
```

4. 回报输出路径、检测到的图类型、实际采用的方式（connected/geometry/picture）

### 2) 批量转换

```bash
python mermaid_to_visio.py --batch <输入目录> -o <输出目录> --theme <theme> --mode auto
```

- 递归扫描 `.mmd` / `.mermaid` / `.md`  
- `.md` 提取首个 \`\`\`mermaid 代码块  
- 输出保留相对目录结构  

### 3) 从对话中的 Mermaid 代码块导出

1. 取出用户给出的 Mermaid 源（去掉 fence）  
2. 写入临时 `.mmd`（建议放在仓库 `out/` 下）  
3. 调用 CLI 生成 `.vsdx`  
4. 告知用户文件路径；需要预览时可先：

```bash
python -c "from mermaid_to_visio import render_png; open(r'out/preview.png','wb').write(render_png(open(r'out/tmp.mmd',encoding='utf-8').read(), theme='redux-color'))"
```

### 4) 打开 GUI（用户要可视化预览/批量点选时）

```bash
python gui_app.py
# 或双击 启动GUI.bat / dist/MermaidToVisio.exe
```

GUI：左侧编辑 → 点选颜色风格 → 右侧预览 →「导出 Visio」或「批量转 Visio」（Ctrl+B）。

## Python API（脚本内调用）

```python
from mermaid_to_visio import convert_mermaid_to_vsdx, detect_kind, render_png

source = open("diagram.mmd", encoding="utf-8").read()
data, method = convert_mermaid_to_vsdx(
    source,
    mode="auto",
    theme="forest",
    connectors="right-angle",
    title="diagram",
)
open("diagram.vsdx", "wb").write(data)
print(detect_kind(source), method)
```

## 交互约定

- 需求模糊时先问：输入文件/目录、输出路径、主题、是否批量  
- **禁止**为“全类型支持”去手写不完整的 Mermaid 解析器；一律走本仓库封装  
- 转换失败时展示完整错误，并尝试 `--mode picture` 兜底（征得用户同意或 auto 已级联）  
- 不要提交 `build/`、`out/`、`__pycache__/` 到 git（见 `.gitignore`）  
- 中文标签预览依赖系统字体回退；若方框乱码，提示安装常见 CJK 字体后重试  

## 验收清单

- [ ] 输出 `.vsdx` 可被 Visio / 兼容软件打开  
- [ ] 状态行或日志中有图类型 + 导出方式  
- [ ] 批量任务报告成功/失败数量  
- [ ] 用户指定的主题已生效  

## 示例

```bash
python mermaid_to_visio.py examples/flowchart.mmd -o out/flowchart.vsdx
python mermaid_to_visio.py examples/er.mmd -o out/er.vsdx --theme forest
python mermaid_to_visio.py --batch ./examples -o ./out/batch --theme dark
```
