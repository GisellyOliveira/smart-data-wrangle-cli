import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict
import shutil
from colorama import Fore, Style

logger = logging.getLogger(__name__)

class FileOrganizer:
    """ 
    Encapsulates the core logic for organizing files from a source
    directory into a categorized destination directory.

    This class is responsible for the pure logic of scanning, hashing,
    and moving files. It is deliberately decoupled from configuration
    loading and user interaction.
    """

    def __init__(self, source_dir: Path, dest_dir: Path):
        """
        Initializes the FileOrganizer with source and destination paths.

        Args:
            source_dir: The directory to scan for files.
            dest_dir: The root directory where categorized subfolders will be created.

        Raises:
            ValueError: If the source directory does not exist or the destination
                        path exists and is not a directory.
        """
        if not source_dir.is_dir():
            raise ValueError(f"Source directory does not exist or is not a directory: {source_dir}")
        if dest_dir.exists() and not dest_dir.is_dir():
            raise ValueError(f"Destination path exists but is not a directory: {dest_dir}")

        self.source_dir = source_dir
        self.dest_dir = dest_dir
        self.files_moved = 0
        self.files_skipped = 0

        print(f"\n{Fore.BLUE}#######################################################################")
        logger.info(f"Core organizer initialized. Source: '{self.source_dir}', Destination: '{self.dest_dir}'")
        print(f"\n{Fore.BLUE}#######################################################################")
    
    def organize(self, extension_map: Dict[str, str], dry_run: bool = False) -> None:
        """
        Executes the main file organization workflow.

        It recursively scans the source directory and processes each file
        according to the provided extension map and dry-run flag.

        Args:
            extension_map: A dictionary mapping file extensions (e.g., '.pdf')
                           to destination folder names (e.g., 'Documents').
            dry_run: If True, simulates all operations without making changes
                     to the filesystem.
        """
        logger.info("Starting file organization process...")
        # Reset counters for this run to ensure the instance is reusable.
        self.files_moved = 0
        self.files_skipped = 0
        
        total_scanned = 0
        for item_path in self.source_dir.rglob('*'):
            if item_path.is_file():
                total_scanned += 1
                self._process_file(item_path, extension_map, dry_run)
        
        self._log_summary(total_scanned, dry_run)
    
    def _process_file(self, file_path: Path, extension_map: Dict[str, str], dry_run: bool) -> None:
        """Determines the destination for a single file and initiates the move."""
        extension = file_path.suffix.lower()
        if not extension or extension not in extension_map:
            logger.debug(f"Ignoring file '{file_path.name}' (unmapped or no extension).")
            return

        dest_folder_name = extension_map[extension]
        destination_category_folder = self.dest_dir / dest_folder_name

        self._move_file_with_deduplication(file_path, destination_category_folder, dry_run)
    
    def _move_file_with_deduplication(self, source_path: Path, dest_folder: Path, dry_run: bool):
        """
        Moves a file, handling potential duplicates by content hashing.

        If a file with the same name exists at the destination, their SHA256
        hashes are compared. Identical files are skipped. Files with the same
        name but different content are renamed with a numerical suffix.
        """
        prospective_dest_path = dest_folder / source_path.name

        # Default to the original path; only change if a conflict is found.
        final_dest_path = prospective_dest_path
        
        if prospective_dest_path.exists():
            source_hash = self._calculate_file_hash(source_path)
            dest_hash = self._calculate_file_hash(prospective_dest_path)
            
            # Skip if hashes are identical, indicating a true duplicate.
            if source_hash and source_hash == dest_hash:
                logger.info(f"Skipping identical file: {source_path.name}")
                self.files_skipped += 1
                return
            
            # If hashes differ or one couldn't be calculated, find a new name.
            final_dest_path = self._get_unique_destination_path(dest_folder, source_path.name)

        if dry_run:
            log_action = "renamed" if final_dest_path.name != source_path.name else "moved"
            logger.info(f"[DRY RUN] File '{source_path.name}' would be {log_action} to '{final_dest_path}'.")
            self.files_moved += 1
            return

        logger.info(f"Moving '{source_path.name}' to '{final_dest_path}'")
        try:
            dest_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_path), str(final_dest_path))
            self.files_moved += 1
        except (shutil.Error, OSError) as e:
            logger.error(f"Could not move file {source_path.name}: {e}")
            self.files_skipped += 1
    
    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """
        Calculates the SHA256 hash of a file, reading it in chunks.

        Returns:
            The hex digest of the hash as a string, or None if an error occurs.
        """
        hasher = hashlib.new("sha256")
        try:
            with file_path.open('rb') as f:
                # Read in 8KB chunks to handle large files efficiently.
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError as e:
            logger.error(f"Could not calculate hash for {file_path}: {e}")
            return None
    
    def _get_unique_destination_path(self, destination_folder: Path, original_file_name: str) -> Path:
        """
        Generates a unique file path if the original already exists by
        appending a numerical suffix (e.g., 'file(1).txt').
        """
        base_name = Path(original_file_name).stem
        extension = Path(original_file_name).suffix
        counter = 1
        potential_dest_path = destination_folder / original_file_name

        while potential_dest_path.exists():
            new_name = f"{base_name}({counter}){extension}"
            potential_dest_path = destination_folder / new_name
            counter += 1
        return potential_dest_path
    
    def _log_summary(self, total_scanned: int, dry_run: bool) -> None:
        """Logs a final summary of the organization process."""
        log_prefix = "Dry run finished." if dry_run else "Organization finished."
        logger.info(f"--- {log_prefix} ---")
        logger.info(f"Total files scanned: {total_scanned}")
        if dry_run:
            logger.info(f"Files that would be moved or renamed: {self.files_moved}")
            logger.info(f"Files that would be skipped (duplicates): {self.files_skipped}")
        else:
            logger.info(f"Files successfully moved or renamed: {self.files_moved}")
            logger.info(f"Identical duplicate files skipped: {self.files_skipped}")
    