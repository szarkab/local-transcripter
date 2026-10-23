"""Source and frozen worker entry point."""
import multiprocessing
from local_transcripter.worker_entry import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
