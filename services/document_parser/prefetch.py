"""Run while building/provisioning the worker, before handling any contracts."""
import os
from pathlib import Path


def main():
    from docling.utils.model_downloader import download_models
    target = Path(os.environ.get('DOCLING_ARTIFACTS_PATH', '/models'))
    download_models(output_dir=target, with_layout=True, with_tableformer=True,
                    with_code_formula=False, with_picture_classifier=False,
                    with_rapidocr=False, progress=False)


if __name__ == '__main__':
    main()
