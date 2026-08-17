"""PyInstaller hook: Magika needs ONNX model + config next to the package."""

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("magika")
