"""
Punto de entrada. Uso:
    python main.py "https://www.youtube.com/watch?v=XXXXXXXX" --clips 5
"""
import argparse

from pipeline import run


def main():
    parser = argparse.ArgumentParser(
        description="Convierte un video largo en clips verticales para Shorts/TikTok/Reels."
    )
    parser.add_argument("url", help="URL del video (YouTube, Vimeo, Twitch, Kick)")
    parser.add_argument("--clips", type=int, default=None, help="Cuantos clips generar (default: config.py)")
    args = parser.parse_args()

    kwargs = {}
    if args.clips:
        kwargs["num_clips"] = args.clips

    run(args.url, **kwargs)


if __name__ == "__main__":
    main()
