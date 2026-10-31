# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("mermaid_render")
hiddenimports += [
    "PIL._tkinter_finder",
    "mermaid_to_visio",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.ttk",
]

excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "keras",
    "scipy",
    "sklearn",
    "scikit-learn",
    "pandas",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "pygments",
    "cv2",
    "onnx",
    "onnxruntime",
    "numba",
    "llvmlite",
    "sympy",
    "transformers",
    "tensorboard",
    "numpy",
    "numpy.core",
    "mkl",
]

DROP_SUBSTR = (
    "mkl_",
    "libmkl",
    "mkl.",
    "omptarget",
    "libiomp",
    "libomp",
    "tbb",
    "torch",
    "cudnn",
    "cublas",
    "scipy",
)


def _keep(item) -> bool:
    # PyInstaller binary/data tuples: (dest_name, src_path, typecode) or similar
    name = str(item[0] if isinstance(item, (tuple, list)) else item).lower()
    src = str(item[1]).lower() if isinstance(item, (tuple, list)) and len(item) > 1 else ""
    blob = name + " " + src
    return not any(s in blob for s in DROP_SUBSTR)


binaries = [b for b in binaries if _keep(b)]
datas = [d for d in datas if _keep(d)]

a = Analysis(
    ["gui_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# Extra filter after analysis picks up conda DLLs via numpy/PIL
a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MermaidToVisio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
