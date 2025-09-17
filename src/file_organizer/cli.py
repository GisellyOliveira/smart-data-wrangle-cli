import argparse
import logging
import sys
from pathlib import Path
from typing import Dict

from colorama import init, Fore, Style

from . import config
from .core import FileOrganizer

init(autoreset=True)

logger = logging.getLogger(__name__)


def setup_logging(level: int):
    """Sets up basic logging for the application."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def handle_interactive_edit(current_map: Dict[str, str]) -> bool:
    """
    Guides the user through an interactive session to review and modify
    existing extension mappings.

    Args:
        current_map: The extension map dictionary to be modified in-place.

    Returns:
        True if any changes were made to the map, False otherwise.
    """
    try:
        print(f"{Fore.BLUE}####################################################################### {Style.RESET_ALL}")
        review_choice = input("Review or modify current extension mappings? (yes/No, default: No): }").strip().lower()
        first_char = review_choice[0] if review_choice else 'n'
        print(f"{Fore.BLUE}####################################################################### {Style.RESET_ALL}")
    except EOFError:
        logger.warning("\nInput stream closed (EOF). Skipping review.")
        return False
        
    if first_char != 'y':
        logger.info("Skipping review of existing mappings.")
        return False
    
    map_changed = False
    logger.info(f"\n{Style.BRIGHT}--- Review/Modify Existing Mappings ---{Style.RESET_ALL}")
    if not current_map:
        logger.info("No mappings currently defined.")
    else:
        for ext, folder in sorted(current_map.items()):
            logger.info(f"  {Fore.CYAN}{ext}{Style.RESET_ALL} -> {Fore.GREEN}{folder}{Style.RESET_ALL}")
    
    while True:
        try:
            ext_to_modify = input("Enter extension to modify (e.g., .pdf), or type 'done' to finish: ").strip().lower()
        except EOFError:
            logger.warning("\nInput stream closed (EOF). Exiting modification mode.")
            break

        if ext_to_modify == 'done':
            break

        if not ext_to_modify.startswith('.') or len(ext_to_modify) < 2:
            if ext_to_modify:
                logger.warning(f"{Fore.YELLOW}Invalid extension format: '{ext_to_modify}'.")
            continue

        if ext_to_modify in current_map:
            current_folder = current_map[ext_to_modify]
            prompt = (
                f"  Extension '{ext_to_modify}' maps to '{current_folder}'.\n"
                f"  New folder (Enter to keep, 'ignore' to remove): "
            )
            try:
                new_folder = input(prompt).strip()
            except EOFError:
                logger.warning("\nInput stream closed (EOF).")
                continue

            if not new_folder:
                logger.info(f"Mapping for '{ext_to_modify}' remains '{current_folder}'.")
            elif new_folder.lower() == 'ignore':
                del current_map[ext_to_modify]
                map_changed = True
                logger.info(f"Mapping for '{ext_to_modify}' removed for this session.")
            else:
                if current_folder != new_folder:
                    current_map[ext_to_modify] = new_folder
                    map_changed = True
                    logger.info(f"Mapping for '{ext_to_modify}' changed to '{new_folder}'.")
        else:
            logger.info(f"Extension '{ext_to_modify}' not currently mapped.")
            
    logger.info("Finished reviewing/modifying mappings.")
    return map_changed


def handle_unmapped_extensions(source_dir: Path, current_map: Dict[str, str]) -> bool:
    """
    Discovers unmapped extensions in the source directory and prompts the
    user for how to categorize them.

    Args:
        source_dir: The source directory to scan for files.
        current_map: The extension map dictionary to be modified in-place.

    Returns:
        True if any new mappings were added, False otherwise.
    """
    logger.info("Scanning for unmapped extensions...")
    found_extensions = {p.suffix.lower() for p in source_dir.rglob('*') if p.is_file() and p.suffix}
    unmapped = sorted(list(found_extensions - set(current_map.keys())))
    
    if not unmapped:
        logger.info("No unmapped extensions found.")
        return False

    map_changed = False
    logger.info(f"\n{Fore.BLUE}###################### New/Unmapped Extensions Found ###################### {Style.RESET_ALL}")
    logger.info("The following unmapped extensions were discovered: " + ", ".join(unmapped))
    print(f"\n{Fore.BLUE}#######################################################################")
    
    for ext in unmapped:
        try:
            prompt = f"Enter target folder for '{Fore.CYAN}{ext}{Style.RESET_ALL}' (or leave blank to ignore): "
            folder_name = input(prompt).strip()
            
            if not folder_name:
                logger.info(f"Extension '{ext}' will be ignored for this session.")
                continue
            
            # Basic validation for folder names to prevent common errors.
            invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
            if any(char in folder_name for char in invalid_chars) or folder_name.startswith('.') or folder_name.endswith('.'):
                logger.warning(f"{Fore.YELLOW}Invalid folder name: '{folder_name}'. Skipping this extension.")
                continue
            
            current_map[ext] = folder_name
            map_changed = True
            logger.info(f"Extension '{ext}' will be organized into '{Fore.GREEN}{folder_name}{Style.RESET_ALL}'.")
        except EOFError:
            logger.warning("\nInput stream closed (EOF). Stopping interactive mapping.")
            break
            
    return map_changed


def main():
    """
    Parses command-line arguments and orchestrates the file organization process.
    """
    parser = argparse.ArgumentParser(
        description="Organizes files from a source directory into categorized subdirectories."
    )
    parser.add_argument("source_dir", type=Path, help="The source directory containing files to organize.")
    parser.add_argument("dest_dir", type=Path, help="The base destination directory for organized sub-folders.")
    parser.add_argument("--dry-run", action="store_true", help="Simulates the organization process without moving files.")
    parser.add_argument("-v", "--verbose", action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.INFO, help="Increase output verbosity to DEBUG level.")

    args = parser.parse_args()

    setup_logging(args.loglevel)

    banner = f"""
{Fore.YELLOW}#######################################################################
######################   Sorting out the chaos   ######################
#######################################################################{Style.RESET_ALL}
    """
    logger.info(banner)

    try:
        extension_map = config.load_extension_map()

        map_changed_by_edit = handle_interactive_edit(extension_map)
        map_changed_by_new = handle_unmapped_extensions(args.source_dir, extension_map)
        map_was_changed = map_changed_by_edit or map_changed_by_new

        organizer = FileOrganizer(args.source_dir, args.dest_dir)
        organizer.organize(extension_map, args.dry_run)

        if map_was_changed and not args.dry_run:
            try:
                save_choice = input("Save these new/updated mappings for future use? (y/N): ").strip().lower()
                if save_choice.startswith('y'):
                    config.save_extension_map(extension_map)
            except EOFError:
                logger.warning("Input stream closed (EOF). Configuration not saved.")

    except (ValueError, FileNotFoundError) as e:
        logger.critical(f"{Fore.RED}Configuration Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"{Fore.RED}An unexpected critical error occurred: {e}", exc_info=True)
        sys.exit(1)
