"""Allowlisted release ZIP; never include private config, dataset or local caches."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


FILES = ('README.md', 'SUBMISSION.md', '.env.example', 'pyproject.toml',
         'requirements.txt', 'requirements-core.txt', 'requirements-llm.txt',
         'requirements-semantic.txt', 'requirements-ui.txt', 'requirements-voice.txt',
         'run.py', 'streamlit_app.py', 'chat_app.py', 'legacy_streamlit_app.py', 'tools/package_submission.py',
         'audio_cases.json', '.streamlit/config.toml', 'report/report.tex',
         'evals/README.md', 'evals/results.md', 'evals/retrieval-experiments.md')
DIRECTORIES = ('src', 'tests', 'sample_outputs', 'audio_samples')
FORBIDDEN_PARTS = {'__pycache__', '.git', '.venv', 'venv', 'artifacts', 'dataset', 'docs', 'node_modules'}


def collect_files(root):
    root = Path(root).resolve()
    selected = []
    for name in FILES:
        path = root / name
        if not path.is_file():
            raise ValueError('Required source/setup file is missing: ' + name)
        selected.append(path)
    for name in DIRECTORIES:
        folder = root / name
        if not folder.is_dir():
            raise ValueError('Required release folder is missing: ' + name)
        selected.extend(p for p in folder.rglob('*') if p.is_file()
                        and not any(part in FORBIDDEN_PARTS for part in p.relative_to(root).parts)
                        and p.suffix.lower() not in {'.pyc', '.pyo'})
    for name in ('report.pdf', 'demo.mp4'):
        if (root / name).is_file():
            selected.append(root / name)
    for path in selected:
        relative = path.relative_to(root)
        if (path.is_symlink() or not path.resolve().is_relative_to(root)
                or any(part in FORBIDDEN_PARTS for part in relative.parts)
                or any(part.startswith('.env') and part != '.env.example' for part in relative.parts)
                or path.name == 'secrets.toml'):
            raise ValueError('Unsafe release path; inspect allowlist')
    return sorted(set(selected))


def package(root, output, *, allow_incomplete=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    selected = collect_files(root)
    missing = [name for name in ('report.pdf', 'demo.mp4')
               if not (root / name).is_file() or (root / name).stat().st_size == 0]
    if missing and not allow_incomplete:
        raise ValueError('Final release refused; missing: ' + ', '.join(missing))
    if any(output == path.resolve() for path in selected):
        raise ValueError('Output must not replace a source file')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest, entries = [], []
    for path in selected:
        data = path.read_bytes()
        name = path.relative_to(root).as_posix()
        # Check before opening the archive, so a rejected key cannot leave a ZIP.
        if path.suffix.lower() in {'.py', '.json', '.md', '.toml', '.txt', '.tex'}:
            import re
            if re.search(rb'AIza[0-9A-Za-z_-]{30,}|\bsk-[A-Za-z0-9_-]{24,}', data):
                raise ValueError('Potential credential found; inspect source locally')
        entries.append((name, data))
        manifest.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    # Exclusive creation: no existing release is silently replaced.
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
        archive.writestr('FILE_MANIFEST.json', json.dumps(manifest, indent=2))
        archive.writestr('SUBMISSION_STATUS.json', json.dumps({
            'structurally_complete': not missing, 'missing_deliverables': missing,
            'author': 'Mrinal Subudhi', 'zip_label': 'Hello_There',
            'repo': 'https://github.com/brindoxx/ZentroMart-AI-Support-Agent',
            'behavioural_readiness_certified': False,
            'required_owner_checks': ['demo duration <=120 seconds', 'public repository',
                                      'report <=4 pages', 'clean external-dataset install', 'final behaviour checks']}, indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive integrity check failed')
    return {'archive': str(output), 'files': len(manifest), 'missing': missing}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-incomplete', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or root / 'dist' / ('Hello_There_voiceops_preview.zip' if args.allow_incomplete else 'Hello_There_voiceops.zip')
    try:
        print(json.dumps(package(root, output, allow_incomplete=args.allow_incomplete), indent=2))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        # Known validation messages never contain candidate credential values.
        if isinstance(error, ValueError):
            print(str(error))
        else:
            print('Packaging could not complete. Check file permissions and use a new output name.')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
