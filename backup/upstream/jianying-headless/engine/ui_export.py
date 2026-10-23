#!/usr/bin/env python3
"""Acceptance for a deliverable exported through Jianying's own export dialog.

This module never renders anything. The editor's UI does the rendering, which is
why this path exists at all: a runtime with no reviewed headless export ABI can
still produce a finished file through the application's public interface.

`plan` freezes what the finished file must look like and proves the registered
draft still equals its verified build. `verify` re-proves that, then checks the
file the UI wrote. Everything a UI run cannot prove on its own -- exact frame
count, full decoding, canvas, frame rate, codecs, and that nobody edited the
draft between planning and exporting -- is checked here, mechanically.

`ui_used` is true in every record this module writes. These results are a
separate evidence tier from the headless native export and are never merged with
it: neither one's acceptance carries over to the other.
"""
import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import jy14_headless as j
import native_compound as compound
import native_edit as edit
import native_export as native
from runtime_profiles import UI_EXPORT_PROFILES

SCHEMA = 'jy14-ui-export/v1'
PLAN_SCHEMA = 'jy14-ui-export-plan/v1'
# Jianying's MP4 preset writes a QuickTime-branded container; the 2026-10-20
# 11.6.0 capture reported `qt  `. The headless exporter's own brand set stays
# untouched, so widening this cannot loosen that path.
CONTAINER_BRANDS = ('isom', 'mp41', 'mp42', 'qt  ')


def live_record(build):
    """Verify the build and prove the registered draft still equals it."""
    build = Path(build).resolve(strict=True)
    record = j.read_json(build / 'build.json')
    schema = record.get('schema')
    j.require(schema in ('jy14-headless-build/v1', edit.BUILD_SCHEMA),
              'UI export acceptance requires a verified headless/edit build')
    # verify_live compares the registered draft against the build, including the
    # four mirrors,媒体 bytes, home registration and the untouched source.
    report = j.verify_live(build) if schema == 'jy14-headless-build/v1' else edit.verify_live(build)
    j.require(report['status'] == 'verified', 'Registered draft does not match its build')
    return build, record, report


def expectations(build, record):
    """Canvas, frame rate, duration and audio the finished file must match."""
    timeline = j.nd.helper()._decrypt_metadata_in_memory(build / 'draft/draft_info.json')
    compound.validate(timeline, edit.basic_validation)
    j.require(timeline.get('duration', 0) > 0 and timeline.get('tracks'), 'Cannot export an empty timeline')
    profile = record['runtime_profile']
    j.require(profile in UI_EXPORT_PROFILES, 'No reviewed UI export acceptance for this build profile')
    runtime = j.nd.validate_runtime()
    j.require(runtime['runtime_profile'] == profile,
              'Build runtime differs from the installed editor; rebuild on the current runtime')
    # Bitrate and timeout are the dialog's own business here, so only the values
    # the finished file is actually checked against are frozen.
    settings = native.settings_for(timeline, 4_000_000, 600)
    audio_expected = any(bool(child['materials'].get('audios')) or any(
        v.get('has_audio', True) for v in child['materials'].get('videos', [])
        if v.get('type') == 'video' and v.get('path')) for _, child in compound.graph(timeline))
    return timeline, runtime, settings, audio_expected


def plan(build, out):
    build, record, report = live_record(build)
    timeline, runtime, settings, audio_expected = expectations(build, record)
    job = Path(out)
    j.require(job.is_absolute() and not job.exists() and not job.is_symlink(),
              'UI export job must be a new absolute directory')
    j.require('work' in job.parts, 'UI export jobs must be under the task work directory')
    j.require(not job.resolve().is_relative_to(build) and not job.resolve().is_relative_to(j.nd.DRAFT_ROOT),
              'UI export job cannot be inside a build or the live draft tree')
    target = Path(record['target'])
    job = j.nd.fresh_directory(job)
    document = {
        'schema': PLAN_SCHEMA, 'ui_used': True, 'renderer': 'Jianying export dialog',
        'build': str(build), 'build_sha256': j.nd.digest(build / 'build.json'),
        'draft': str(target), 'draft_name': target.name,
        'runtime': runtime, 'settings': settings,
        'duration_us': timeline['duration'], 'audio_expected': audio_expected,
        'expected_output': str(job / (target.name + '.mp4')),
        'accepted_container_brands': list(CONTAINER_BRANDS),
        'live_draft_matches_build': True,
        'readback_before_export': report,
        # Unlike the headless exporter, this path has to open the draft, and the
        # editor writes backups, covers and a fresh save while it is open. The
        # manifest is frozen here so `verify` can report exactly what moved.
        'draft_files_before': j.files_manifest(target),
        'draft_is_modified_by_exporting': True,
        'dialog_settings_required': {
            # The dialog lists whole frame rates without a decimal part.
            '格式': 'MP4', '分辨率': '原始',
            '帧率': str(int(settings['fps'])) if float(settings['fps']).is_integer() else str(settings['fps']),
            '导出至': str(job),
            '音频导出': '保持关闭（那是单独的音频文件，不是视频里的音轨）',
            '一键超清': '保持关闭',
        },
        'operator_notes': [
            'Export the registered draft from the editor; do not edit it first.',
            'The finished screen offers publishing to a third-party platform. Close it; never publish.',
        ],
    }
    j.write(job / 'plan.json', document)
    return document


def probe(path):
    return json.loads(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], timeout=120))


def validate_container(info, settings, duration_us, audio_expected):
    """Reuse the headless frame/codec checks, with this path's own brand set."""
    brand = info.get('format', {}).get('tags', {}).get('major_brand')
    j.require(brand in CONTAINER_BRANDS, 'UI export container brand is not a reviewed MP4 brand: ' + str(brand))
    patched = json.loads(json.dumps(info))
    # validate_probe owns the exact frame-count and codec policy. Only the brand
    # differs for a UI export, and it was checked exactly above.
    patched['format']['tags']['major_brand'] = 'isom'
    media = native.validate_probe(patched, settings, duration_us, audio_expected)
    media['major_brand'] = brand
    media['container_writer'] = 'Jianying export dialog'
    return media


def draft_changes(document, target):
    """What the editor touched in the draft while it was open for exporting.

    Reported, never enforced: opening a draft is how this path renders at all.
    The build/live comparison above still decides whether the content matched.
    """
    before = document.get('draft_files_before') or {}
    after = j.files_manifest(target)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(name for name in set(before) & set(after) if before[name] != after[name])
    return {'added': len(added), 'removed': len(removed), 'changed': len(changed),
            'changed_names': changed[:20], 'added_names': added[:20], 'removed_names': removed[:20],
            'note': 'The editor rewrites backups, covers and the saved timeline while the draft '
                    'is open. A draft that is the recorded source of an edit build will fail that '
                    "build's source-unchanged check afterwards."}


def verify(job, video=None, report=None):
    job = Path(job).resolve(strict=True)
    document = j.read_json(job / 'plan.json')
    j.require(document.get('schema') == PLAN_SCHEMA and document.get('ui_used') is True,
              'Unknown UI export plan')
    build = Path(document['build'])
    j.require(j.nd.digest(build / 'build.json') == document['build_sha256'], 'Build changed since planning')
    # The UI exports the live draft, not the frozen snapshot, so this has to hold
    # at export time too, not just when the job was planned.
    build, record, after = live_record(build)
    timeline, runtime, settings, audio_expected = expectations(build, record)
    j.require(settings == document['settings'] and timeline['duration'] == document['duration_us']
              and audio_expected == document['audio_expected'],
              'Draft canvas, frame rate, duration or audio changed since planning')
    j.require(runtime['runtime_profile'] == document['runtime']['runtime_profile']
              and runtime['libvideoeditor_sha256'] == document['runtime']['libvideoeditor_sha256'],
              'Editor runtime changed since planning')

    output = Path(video).resolve(strict=True) if video else Path(document['expected_output'])
    j.require(output.is_file() and not output.is_symlink(), 'No exported file at ' + str(output))
    j.require(output.stat().st_size > 0, 'Exported file is empty')
    # Each attempt keeps its own evidence; a rejected export is never overwritten
    # by a later one, and the job directory records every check that was run.
    attempt = j.nd.fresh_directory(job / ('attempt-%03d' % (1 + sum(
        1 for path in job.iterdir() if path.is_dir() and path.name.startswith('attempt-')))))
    started = time.monotonic()
    info = probe(output)
    j.write(attempt / 'ffprobe.json', info)
    media = validate_container(info, settings, timeline['duration'], audio_expected)
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'],
                             capture_output=True, timeout=3600)
    j.write(attempt / 'decode.stderr.log', decoded.stderr)
    j.require(decoded.returncode == 0, 'Exported MP4 did not fully decode')

    evidence = {
        'schema': SCHEMA, 'status': 'encoded-and-decoded', 'ui_used': True,
        'renderer': 'Jianying export dialog', 'container_writer': 'Jianying export dialog',
        'headless_native_export_used': False, 'external_ffmpeg_composition': False,
        'network_allowed': False, 'published_to_any_platform': False,
        'build': str(build), 'draft': document['draft'], 'runtime': runtime,
        'settings': settings, 'media': media, 'full_decode_passed': True,
        'output': str(output), 'output_sha256': j.nd.digest(output),
        'output_bytes': output.stat().st_size,
        'live_draft_matched_build_before_export': document['readback_before_export']['status'],
        'live_draft_matched_build_after_export': after['status'],
        'source_files_unchanged': after.get('source_files_unchanged', True),
        'acceptance_boundaries': native.supported_features(timeline),
        'draft_changes_made_by_exporting': draft_changes(document, Path(document['draft'])),
        'visual_content_acceptance': 'requires viewing the actual output',
        'evidence_tier': 'UI export; not interchangeable with the headless native export',
        'elapsed_seconds': round(time.monotonic() - started, 3),
    }
    evidence['attempt'] = attempt.name
    j.write(attempt / 'result.json', evidence)
    if report:
        j.write(Path(report), evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan', help='Freeze what the UI must export, and prove the draft matches its build')
    p.add_argument('--build', required=True)
    p.add_argument('--out', required=True, help='New absolute job directory under work/')
    p = sub.add_parser('verify', help='Check the file the export dialog wrote')
    p.add_argument('--job', required=True)
    p.add_argument('--video', help='Exported file, when it is not at the planned path')
    p.add_argument('--report', help='Also write the evidence here')
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            result = plan(args.build, args.out)
            print(json.dumps({k: result[k] for k in (
                'schema', 'ui_used', 'draft_name', 'settings', 'duration_us',
                'expected_output', 'dialog_settings_required', 'operator_notes')},
                ensure_ascii=False, indent=2))
        else:
            result = verify(args.job, args.video, args.report)
            print(json.dumps({k: result[k] for k in (
                'status', 'ui_used', 'output', 'media', 'full_decode_passed',
                'live_draft_matched_build_after_export', 'evidence_tier')},
                ensure_ascii=False, indent=2))
    except Exception as error:
        print('UI export acceptance failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
