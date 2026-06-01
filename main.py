from src.agent.loop import run_agent
from src.providers import get_model_priorities

import logging
import sys

# Branded Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("vraksha.log", encoding="utf-8"),
    ]
)

# Suppress external noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pydantic_ai").setLevel(logging.INFO)

logger = logging.getLogger("Vraksha")

# Vraksha Palette (ANSI Colors)
A = '\033[38;5;38m'    # accent · teal
G = '\033[38;5;121m'   # success · green
R = '\033[38;5;203m'   # error · red
Y = '\033[38;5;215m'   # warning · yellow
M = '\033[38;5;244m'   # muted · gray
D = '\033[38;5;238m'   # dim · dark gray
T = '\033[38;5;254m'   # text · white
B = '\033[1m'          # bold
NC = '\033[0m'         # no color

# System Glyphs
GL_LOGO = "▲"
GL_CHECK = "✓"
GL_DIAMOND = "◆"
GL_ARROW = "›"
GL_DOT = "·"

def pre_flight_audit():
    """Ensures the environment is ready for takeoff."""
    logger.info("--- Vraksha Pre-Flight Audit ---")
    
    # 1. Check for available LLM providers
    priorities = get_model_priorities("orchestrator")
    if not priorities:
        print(f"\n  {R}{GL_DIAMOND}{NC}  {B}{T}COGNITIVE READINESS ALERT{NC}")
        print(f"  {D}────────────────────────────────────────────────────────────────{NC}")
        print(f"  {M}I found no valid API keys for Anthropic, OpenAI, or Google.{NC}")
        print(f"  {M}I cannot initialize my Central Nervous System without them.{NC}\n")
        print(f"  {B}{T}ACTION REQUIRED:{NC}")
        print(f"  {A}{GL_ARROW}{NC}  {M}Check your {NC}{B}.env{NC}{M} file in the project root.{NC}")
        print(f"  {A}{GL_ARROW}{NC}  {M}Ensure keys have credits and are not expired.{NC}")
        print(f"  {A}{GL_ARROW}{NC}  {M}Run {NC}{B}vraksha build{NC}{M} to synchronize your environment.{NC}")
        print(f"  {D}────────────────────────────────────────────────────────────────{NC}\n")
        logger.error("Audit failed: No API keys found.")
        sys.exit(1)

    print(f"  {G}{GL_CHECK}{NC}  {B}{T}Identity Verified{NC}  {D}{GL_DOT}{NC}  {M}Primary: {priorities[0]}{NC}")
    if len(priorities) > 1:
        fallback_names = ", ".join(str(m) for m in priorities[1:])
        print(f"  {A}{GL_DIAMOND}{NC}  {B}{T}Resilience Active{NC}  {D}{GL_DOT}{NC}  {M}Fallbacks: {fallback_names}{NC}")
    
    logger.info(f"Identity Verified. Primary Provider: {priorities[0]}")
    if len(priorities) > 1:
        logger.info(f"Fallback Chain Active: {', '.join(str(m) for m in priorities[1:])}")

if __name__ == "__main__":
    try:
        # Perform security and environment checks
        pre_flight_audit()
        
        print("\033[38;2;0;212;170m▲ Vraksha CNS Initialized\033[0m")
        run_agent()

    except KeyboardInterrupt:
        logger.info("Session interrupted by user.")
        print("\n\033[38;5;244mSession terminated. Vraksha is entering standby.\033[0m")

    except Exception as e:
        logger.exception(f"Fatal error during execution: {e}")
        print(f"\n\033[38;5;203m[!] FATAL ERROR: {e}\033[0m")
        print("Check vraksha.log for the full traceback.")
        
    finally:
        logger.info("--- Vraksha Session Ended ---")
