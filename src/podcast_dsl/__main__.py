#!/usr/bin/env python3
"""
CLI entry point for podcast DSL renderer.
"""

import argparse
from .video_renderer import render_dsl


def main():
    parser = argparse.ArgumentParser(
        description='Render podcast videos using DSL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Render from file
  python -m podcast_dsl segment_2_test.dsl -o output.mp4

  # Render from stdin
  cat segment_2_test.dsl | python -m podcast_dsl -o output.mp4
  echo '$segment2/0' | python -m podcast_dsl - -o output.mp4

  # Dry run (calculate duration without rendering)
  python -m podcast_dsl segment_2_test.dsl --dry-run

  # Auto-generate camera cuts based on speaker
  python -m podcast_dsl segment_2_test.dsl --auto-cuts -o output.mp4

  # Test rendering from middle (skip 10 clips, render next 5 clips)
  python -m podcast_dsl segment_2_test.dsl --skip 10 --limit 5 -o test.mp4
        """
    )
    parser.add_argument('dsl_file', nargs='?', default='-',
                        help='DSL file to render (use "-" or omit for stdin)')
    parser.add_argument('--output', '-o', default='../outputs/dsl_output.mp4',
                        help='Output video file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Calculate total duration without rendering')
    parser.add_argument('--auto-cuts', action='store_true',
                        help='Auto-insert cameras: Ben open, intro/crosstalk wide, 5s min / random wide / <1s hold')
    parser.add_argument('--auto-cuts-legacy', action='store_true',
                        help='Use older auto-cuts (random wide, minimum 5s per angle, short-hold)')
    parser.add_argument('--skip', type=int, default=0,
                        help='Skip first N clips (for testing)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Render only M clips after skipping (for testing)')
    parser.add_argument('--max-seconds', type=float, default=None,
                        help='Render only the first N seconds of timeline (for testing)')
    parser.add_argument('--debug', action='store_true',
                        help='Save intermediate segment files to debug_segments/ folder for inspection')
    parser.add_argument('--workers', type=int, default=8,
                        help='Number of parallel workers for rendering (default: 8)')
    parser.add_argument('--render-all-cams', action='store_true',
                        help='Render separate output files for each camera feed instead of cutting between cameras')
    parser.add_argument('--margin', type=float, default=0.0,
                        help='Extra margin in seconds to add when slicing clips (default: 0.0)')

    args = parser.parse_args()

    if args.auto_cuts and args.auto_cuts_legacy:
        parser.error('Use only one of --auto-cuts and --auto-cuts-legacy')

    # Render all cams mode takes precedence
    if args.render_all_cams:
        from .video_renderer import render_all_cams
        render_all_cams(args.dsl_file, args.output, dry_run=args.dry_run,
                       skip_clips=args.skip, limit_clips=args.limit, max_seconds=args.max_seconds, debug=args.debug,
                       num_workers=args.workers, margin=args.margin)
    else:
        render_dsl(
            args.dsl_file,
            args.output,
            dry_run=args.dry_run,
            auto_cuts=args.auto_cuts or args.auto_cuts_legacy,
            auto_cuts_legacy=args.auto_cuts_legacy,
            skip_clips=args.skip,
            limit_clips=args.limit,
            max_seconds=args.max_seconds,
            debug=args.debug,
            num_workers=args.workers,
            margin=args.margin,
        )


if __name__ == '__main__':
    main()
