import logging
import sys

def setup_logging(verbose: bool = False) -> None:
    """Configure logging with optional verbosity"""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            # Add file handler in production
            # logging.FileHandler("cv_parser.log")
        ]
    )
    # Reduce third-party log noise
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.INFO)