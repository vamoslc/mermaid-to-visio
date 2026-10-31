#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mermaid → Microsoft Visio (.vsdx)

Supports any Mermaid diagram type that the renderer can draw, including:
  flowchart / graph, sequenceDiagram, classDiagram, erDiagram, stateDiagram,
  gantt, pie, mindmap, timeline, gitGraph, journey, quadrantChart, sankey,
  xychart, block, C4, requirement, architecture, ...

Strategy (auto):
  1) Connected editable VSDX via mermaid-render (flowchart / sequence / state / class)
  2) Else: Mermaid → SVG → geometry VSDX (svg_to_vsdx) — all other types
  3) Else: Mermaid → PNG embedded as a Visio picture page (last resort)

Usage:
  python mermaid_to_visio.py diagram.mmd
  python mermaid_to_visio.py diagram.mmd -o out.vsdx
  python mermaid_to_visio.py -  -o out.vsdx < diagram.mmd
  python mermaid_to_visio.py diagram.mmd --mode connected|geometry|picture|auto
  python mermaid_to_visio.py --batch ./diagrams -o ./vsdx_out

Requires: pip install mermaid-render
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional
from xml.sax.saxutils import escape

# ---------------------------------------------------------------------------
# Diagram type detection (for logging / mode hints)
# ---------------------------------------------------------------------------

_DIAGRAM_HEAD = re.compile(
    r"^\s*(?:%%\{.*?\}%%\s*)?"
    r"(?P<kind>"
    r"flowchart|graph|sequenceDiagram|classDiagram|erDiagram|stateDiagram(?:-v2)?"
    r"|gantt|pie|mindmap|timeline|gitGraph|journey|quadrantChart|sankey(?:-beta)?"
    r"|xychart(?:-beta)?|block(?:-beta)?|C4Context|C4Container|C4Component|C4Dynamic"
    r"|C4Deployment|requirementDiagram|architecture(?:-beta)?|packet(?:-beta)?"
    r"|kanban|radar(?:-beta)?|treemap(?:-beta)?"
    r")\b",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

CONNECTED_KINDS = {
    "flowchart",
    "graph",
    "sequencediagram",
    "classdiagram",
    "statediagram",
    "statediagram-v2",
}


def detect_kind(source: str) -> str:
    m = _DIAGRAM_HEAD.search(source)
    return (m.group("kind") if m else "unknown").strip()


def strip_fences(text: str) -> str:
    """Allow ```mermaid ... ``` wrappers."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


# ---------------------------------------------------------------------------
# mermaid-render backend
# ---------------------------------------------------------------------------

def _import_mermaid_render():
    try:
        import mermaid_render as mr  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "缺少依赖 mermaid-render。请先安装：\n"
            "  pip install mermaid-render\n"
            "或使用镜像：\n"
            "  pip install mermaid-render -i https://pypi.tuna.tsinghua.edu.cn/simple"
        ) from e
    return mr


def render_connected_vsdx(
    source: str,
    *,
    theme: str = "redux-color",
    connectors: str = "right-angle",
) -> bytes:
    mr = _import_mermaid_render()
    kwargs = {"format": "vsdx", "theme": theme, "visio_connectors": connectors}
    try:
        return mr.convert(source, **kwargs)
    except TypeError:
        # older signature
        return mr.mermaid_to_vsdx(source, theme=theme, visio_connectors=connectors)


def render_svg(source: str, *, theme: str = "redux-color") -> str:
    """Return SVG markup as str (svg_to_vsdx requires text, not bytes)."""
    mr = _import_mermaid_render()
    try:
        data = mr.convert(source, format="svg", theme=theme)
    except TypeError:
        data = mr.mermaid_to_svg(source, theme=theme)
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return data


def render_png(source: str, *, theme: str = "redux-color", scale: float = 2.0) -> bytes:
    mr = _import_mermaid_render()
    try:
        return mr.convert(source, format="png", theme=theme, scale=scale, background="white")
    except TypeError:
        return mr.mermaid_to_png(source, theme=theme, scale=scale)


def svg_to_geometry_vsdx(svg: bytes | str) -> bytes:
    """Geometry-only VSDX: works for any Mermaid SVG (no glue/connectors)."""
    mr = _import_mermaid_render()
    if not hasattr(mr, "svg_to_vsdx"):
        try:
            from mermaid_render import svg_to_vsdx as _fn  # type: ignore
        except ImportError as e:
            raise RuntimeError("当前 mermaid-render 无 svg_to_vsdx，请升级到 >=0.14") from e
    else:
        _fn = mr.svg_to_vsdx
    if isinstance(svg, bytes):
        svg = svg.decode("utf-8")
    return _fn(svg)


# ---------------------------------------------------------------------------
# Picture-page VSDX fallback (pure stdlib) — always works if we have PNG bytes
# ---------------------------------------------------------------------------

_PX_PER_IN = 96.0


def _png_size(png: bytes) -> tuple[int, int]:
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是有效的 PNG")
    w = int.from_bytes(png[16:20], "big")
    h = int.from_bytes(png[20:24], "big")
    return w, h


def png_to_picture_vsdx(png: bytes, title: str = "Mermaid") -> bytes:
    """Embed PNG as a single Visio Foreign picture shape (opens in Visio)."""
    w_px, h_px = _png_size(png)
    # Visio page units: inches
    width_in = max(w_px / _PX_PER_IN, 0.5)
    height_in = max(h_px / _PX_PER_IN, 0.5)
    page_w = width_in + 0.5
    page_h = height_in + 0.5
    pin_x = page_w / 2
    pin_y = page_h / 2
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = escape(title)[:200]

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
  <Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
  <Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
  <Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
</Types>
"""
    rels_root = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>
</Relationships>
"""
    doc = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
  <DocumentSettings TopPage="0" DefaultTextStyle="3" DefaultLineStyle="3" DefaultFillStyle="3" DefaultGuideStyle="4"/>
  <StyleSheets>
    <StyleSheet ID="0" NameU="No Style" IsCustomNameU="1" Name="No Style" IsCustomName="1"/>
    <StyleSheet ID="3" NameU="Normal" IsCustomNameU="1" Name="Normal" IsCustomName="1"/>
    <StyleSheet ID="4" NameU="Guide" IsCustomNameU="1" Name="Guide" IsCustomName="1"/>
  </StyleSheets>
</VisioDocument>
"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
  <Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/>
</Relationships>
"""
    pages = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
  <Page ID="0" NameU="Page-1" IsCustomNameU="1" Name="Page-1" IsCustomName="1" ViewScale="1" ViewCenterX="{cx}" ViewCenterY="{cy}">
    <PageSheet LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PageWidth" V="{pw}"/>
      <Cell N="PageHeight" V="{ph}"/>
      <Cell N="ShdwObliqueAngle" V="0"/>
      <Cell N="ShdwOffsetX" V="0"/>
      <Cell N="ShdwOffsetY" V="0"/>
      <Cell N="PageScale" V="1" U="IN_F"/>
      <Cell N="DrawingScale" V="1" U="IN_F"/>
      <Cell N="DrawingSizeType" V="0"/>
      <Cell N="DrawingScaleType" V="0"/>
      <Cell N="InhibitSnap" V="0"/>
      <Cell N="PageLockReplace" V="0" U="BOOL"/>
      <Cell N="PageLockDuplicate" V="0" U="BOOL"/>
      <Cell N="UIVisibility" V="0"/>
    </PageSheet>
    <Rel r:id="rId1"/>
  </Page>
</Pages>
""".format(pw=page_w, ph=page_h, cx=pin_x, cy=pin_y)

    pages_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>
</Relationships>
"""

    # ForeignData picture shape; image related via rIdImg
    page1 = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
  <Shapes>
    <Shape ID="1" Type="Foreign" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{pin_x}"/>
      <Cell N="PinY" V="{pin_y}"/>
      <Cell N="Width" V="{width_in}"/>
      <Cell N="Height" V="{height_in}"/>
      <Cell N="LocPinX" V="{width_in/2}" F="Width*0.5"/>
      <Cell N="LocPinY" V="{height_in/2}" F="Height*0.5"/>
      <Cell N="Angle" V="0"/>
      <Cell N="FlipX" V="0"/>
      <Cell N="FlipY" V="0"/>
      <Cell N="ImgOffsetX" V="0" F="ImgWidth*0"/>
      <Cell N="ImgOffsetY" V="0" F="ImgHeight*0"/>
      <Cell N="ImgWidth" V="{width_in}" F="Width*1"/>
      <Cell N="ImgHeight" V="{height_in}" F="Height*1"/>
      <ForeignData ForeignType="Bitmap" CompressionType="PNG">
        <Rel r:id="rIdImg"/>
      </ForeignData>
    </Shape>
  </Shapes>
</PageContents>
"""
    page1_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImg" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>
"""
    windows = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Windows ClientWidth="1920" ClientHeight="1080" xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Window ID="0" WindowType="Drawing" WindowState="1073741824" WindowLeft="0" WindowTop="0"
   WindowWidth="1920" WindowHeight="1080" ContainerType="Page" Page="0"
   ViewScale="1" ViewCenterX="{pin_x}" ViewCenterY="{pin_y}"/>
</Windows>
"""
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{safe_title}</dc:title>
  <dc:creator>mermaid_to_visio</dc:creator>
  <cp:lastModifiedBy>mermaid_to_visio</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>mermaid_to_visio</Application>
</Properties>
"""
    custom = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>
"""

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels_root)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("docProps/custom.xml", custom)
        z.writestr("visio/document.xml", doc)
        z.writestr("visio/_rels/document.xml.rels", doc_rels)
        z.writestr("visio/pages/pages.xml", pages)
        z.writestr("visio/pages/_rels/pages.xml.rels", pages_rels)
        z.writestr("visio/pages/page1.xml", page1)
        z.writestr("visio/pages/_rels/page1.xml.rels", page1_rels)
        z.writestr("visio/windows.xml", windows)
        z.writestr("visio/media/image1.png", png)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Conversion orchestration
# ---------------------------------------------------------------------------

def convert_mermaid_to_vsdx(
    source: str,
    *,
    mode: str = "auto",
    theme: str = "redux-color",
    connectors: str = "right-angle",
    title: str = "Mermaid",
    scale: float = 2.0,
) -> tuple[bytes, str]:
    """
    Returns (vsdx_bytes, method) where method is connected|geometry|picture.
    """
    source = strip_fences(source)
    if not source.strip():
        raise ValueError("空的 Mermaid 源")

    kind = detect_kind(source).lower()
    mode = mode.lower().strip()

    def try_connected() -> bytes:
        return render_connected_vsdx(source, theme=theme, connectors=connectors)

    def try_geometry() -> bytes:
        svg = render_svg(source, theme=theme)
        return svg_to_geometry_vsdx(svg)

    def try_picture() -> bytes:
        png = render_png(source, theme=theme, scale=scale)
        return png_to_picture_vsdx(png, title=title)

    errors: list[str] = []

    if mode == "connected":
        return try_connected(), "connected"

    if mode == "geometry":
        return try_geometry(), "geometry"

    if mode == "picture":
        return try_picture(), "picture"

    # auto: connected for supported kinds, else geometry, else picture
    if kind in CONNECTED_KINDS:
        try:
            return try_connected(), "connected"
        except Exception as e:  # noqa: BLE001 — fall through to geometry
            errors.append(f"connected: {e}")

    try:
        return try_geometry(), "geometry"
    except Exception as e:  # noqa: BLE001
        errors.append(f"geometry: {e}")

    try:
        return try_picture(), "picture"
    except Exception as e:  # noqa: BLE001
        errors.append(f"picture: {e}")
        raise RuntimeError("转换失败：\n  - " + "\n  - ".join(errors)) from e


def default_out_path(src: Path) -> Path:
    return src.with_suffix(".vsdx")


def iter_inputs(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for p in sorted(path.rglob("*")):
        if p.suffix.lower() in {".mmd", ".mermaid", ".md"} and p.is_file():
            yield p


def read_source(path: Optional[Path]) -> str:
    if path is None or str(path) == "-":
        return sys.stdin.read()
    text = path.read_text(encoding="utf-8")
    # For .md: extract first ```mermaid fence if present
    if path.suffix.lower() == ".md":
        m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1)
    return text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert any Mermaid diagram to Visio .vsdx "
        "(flowchart / class / ER / sequence / state / gantt / pie / …)",
    )
    p.add_argument(
        "input",
        nargs="?",
        default="-",
        help="输入 .mmd / .mermaid / .md，或 - 读 stdin；配合 --batch 时为目录",
    )
    p.add_argument("-o", "--output", help="输出 .vsdx 路径；批量时为输出目录")
    p.add_argument(
        "--mode",
        choices=("auto", "connected", "geometry", "picture"),
        default="auto",
        help="auto=可编辑优先；connected=仅语义连接；geometry=SVG几何；picture=整图嵌入",
    )
    p.add_argument("--theme", default="redux-color",
                   help="redux-color|default|dark|neutral|forest")
    p.add_argument(
        "--connectors",
        default="right-angle",
        choices=("right-angle", "straight", "mermaid"),
        help="仅对 connected 模式的 flowchart/state/class 生效",
    )
    p.add_argument("--scale", type=float, default=2.0, help="picture 模式 PNG 倍率")
    p.add_argument("--batch", action="store_true", help="批量转换目录下所有 mermaid 文件")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    in_arg = args.input

    if args.batch:
        root = Path(in_arg)
        if not root.exists():
            print(f"目录不存在: {root}", file=sys.stderr)
            return 2
        out_dir = Path(args.output) if args.output else root / "vsdx_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        n_ok = n_fail = 0
        for src in iter_inputs(root):
            rel = src.relative_to(root)
            dest = out_dir / rel.with_suffix(".vsdx")
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                source = read_source(src)
                data, method = convert_mermaid_to_vsdx(
                    source,
                    mode=args.mode,
                    theme=args.theme,
                    connectors=args.connectors,
                    title=src.stem,
                    scale=args.scale,
                )
                dest.write_bytes(data)
                n_ok += 1
                if not args.quiet:
                    print(f"[OK] {src} -> {dest}  ({method}, {detect_kind(source)})")
            except Exception as e:  # noqa: BLE001
                n_fail += 1
                print(f"[FAIL] {src}: {e}", file=sys.stderr)
        if not args.quiet:
            print(f"完成: {n_ok} 成功, {n_fail} 失败")
        return 0 if n_fail == 0 else 1

    src_path: Optional[Path]
    if in_arg == "-":
        src_path = None
        out = Path(args.output) if args.output else Path("mermaid_out.vsdx")
        title = out.stem
    else:
        src_path = Path(in_arg)
        if not src_path.exists() and in_arg != "-":
            print(f"文件不存在: {src_path}", file=sys.stderr)
            return 2
        out = Path(args.output) if args.output else default_out_path(src_path)
        title = src_path.stem

    source = read_source(src_path)
    kind = detect_kind(source)
    data, method = convert_mermaid_to_vsdx(
        source,
        mode=args.mode,
        theme=args.theme,
        connectors=args.connectors,
        title=title,
        scale=args.scale,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    if not args.quiet:
        print(f"已生成: {out.resolve()}")
        print(f"类型: {kind}  方式: {method}  大小: {len(data)} bytes")
        hint = {
            "connected": "可编辑形状 + 粘合连接线（推荐）",
            "geometry": "SVG 几何导入为 Visio 形状（无语义粘合）",
            "picture": "整页 PNG 嵌入（保真，形状不可拆）",
        }[method]
        print(f"说明: {hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
