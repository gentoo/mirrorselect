def main():
    try:
        import sys
        from mirrorselect.main import MirrorSelect
        MirrorSelect().main(sys.argv)
    except KeyboardInterrupt:
        import signal
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.raise_signal(signal.SIGINT)
