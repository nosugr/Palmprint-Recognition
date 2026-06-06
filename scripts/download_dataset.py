"""下载 Kaggle 掌纹数据集（需配置 ~/.kaggle/kaggle.json）。

DESIGN.md 推荐：
  - saqibshoaibdz/palm-dataset
  - shyambhu/hands-and-palm-images-dataset
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


DATASETS = {
    "palm": "saqibshoaibdz/palm-dataset",
    "hands": "shyambhu/hands-and-palm-images-dataset",
}

# Tongji 官方发布（Google Drive）。ROI 为作者算法裁好的 128×128 掌纹，
# 直接用于算法标定（推荐）；original 为 800×600 原始整手图。
TONGJI_GDRIVE = {
    "tongji-roi": "1KZCXi6zAk5mZ1nQHFdeYHboAII3DOjls",
    "tongji-original": "15hEsOm0fZKUHpFNChPSjwiRfMczxcnVQ",
}


def has_kaggle_auth() -> bool:
    if os.environ.get("KAGGLE_API_TOKEN"):
        return True
    if Path.home().joinpath(".kaggle", "kaggle.json").exists():
        return True
    if Path.home().joinpath(".kaggle", "access_token").exists():
        return True
    return False


def ensure_kaggle() -> str:
    kaggle = shutil.which("kaggle")
    if kaggle:
        return kaggle
    print("kaggle CLI not found, installing into venv …")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "kaggle"])
    venv_kaggle = Path(sys.executable).parent / "kaggle"
    if venv_kaggle.exists():
        return str(venv_kaggle)
    raise RuntimeError("kaggle installed but binary not found; add venv/bin to PATH")


def ensure_gdown() -> object:
    try:
        import gdown  # type: ignore
    except ModuleNotFoundError:
        print("gdown not found, installing into venv …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])
        import gdown  # type: ignore
    return gdown


def download_tongji(name: str, out: Path) -> None:
    """从 Google Drive 下载 Tongji 官方数据集（RAR），需手动用 unar/unrar 解压。"""
    gdown = ensure_gdown()
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{name}.rar"
    print(f"Downloading {name} → {dst}")
    gdown.download(id=TONGJI_GDRIVE[name], output=str(dst), quiet=False)
    print(f"Done → {dst}")
    print("Extract with:  unar -o data/raw/palm_roi  " + str(dst))
    print("(brew install unar / apt install unar 如未安装)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download palm datasets")
    parser.add_argument(
        "--dataset",
        choices=list(DATASETS.keys()) + list(TONGJI_GDRIVE.keys()),
        default="tongji-roi",
        help="which dataset to download (tongji-roi 推荐：官方裁好的 ROI)",
    )
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    if args.dataset in TONGJI_GDRIVE:
        download_tongji(args.dataset, args.out)
        return

    cred = Path.home() / ".kaggle" / "kaggle.json"
    if not has_kaggle_auth():
        print("ERROR: Kaggle credentials not found.")
        print("  Option A: export KAGGLE_API_TOKEN=<token from Kaggle settings>")
        print("  Option B: save ~/.kaggle/kaggle.json (legacy) or ~/.kaggle/access_token")
        print("")
        print("Alternatively, manually download zip from Kaggle and unzip to data/raw/palm/")
        sys.exit(1)

    slug = DATASETS[args.dataset]
    out = args.out / args.dataset
    out.mkdir(parents=True, exist_ok=True)

    kaggle = ensure_kaggle()
    cmd = [kaggle, "datasets", "download", "-d", slug, "-p", str(out), "--unzip"]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print(f"Done → {out}")


if __name__ == "__main__":
    main()
